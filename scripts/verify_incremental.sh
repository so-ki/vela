#!/usr/bin/env bash
# Incremental regen after material return
set -euo pipefail
API="${VELA_API:-http://127.0.0.1:8000/api/v1}"

login() {
  curl -sf -X POST "$API/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"Demo1234!\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

BIZ=$(login biz@demo.vela)
LEGAL=$(login legal@demo.vela)

SUB=$(curl -sf -X POST "$API/scenarios/submit-materials" -H "Authorization: Bearer $BIZ" \
  -F 'payload={"project_name":"增量协查测试工厂","description":"计划在巴西圣保罗州绿地设厂，新建新能源制造工厂并分期雇佣当地员工。","scope_acknowledged":true,"scope_notice_version":"scope-notice-v2"}' \
  -F 'files=@scripts/fixtures/sample_storage_project.txt')
SID=$(echo "$SUB" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
PROPOSAL_HASH=$(echo "$SUB" | python3 -c "import sys,json; print(json.load(sys.stdin)['scenario_scope']['proposed']['proposal_hash'])")

FIRST=$(curl -sf -X POST "$API/scenarios/$SID/confirm-scope" \
  -H "Authorization: Bearer $LEGAL" -H 'Content-Type: application/json' \
  -d "{\"compliance_dimensions\":[\"labor\",\"foreign_investment\",\"tax\",\"environment\",\"industry_access\"],\"expected_proposal_hash\":\"$PROPOSAL_HASH\",\"fit_decision\":\"accept_warning\",\"polish\":false}")
FIRST_PACK=$(echo "$FIRST" | python3 -c "import sys,json; s=json.load(sys.stdin)['scenario_scope']['snapshot']; print('|'.join([s['capability_pack_id'],s['capability_pack_version'],s['capability_pack_hash'],s['rules_artifact_hash'],s['corpus_artifact_hash']]))")

curl -sf -X POST "$API/scenarios/$SID/review/init" -H "Authorization: Bearer $LEGAL" >/dev/null
curl -sf -X PATCH "$API/scenarios/$SID/review/items/FOR-001" \
  -H "Authorization: Bearer $LEGAL" -H 'Content-Type: application/json' \
  -d '{"decision":"approved","comment":"结构清晰"}' >/dev/null

curl -sf -X POST "$API/scenarios/$SID/return-materials" \
  -H "Authorization: Bearer $LEGAL" -H 'Content-Type: application/json' \
  -d '{"compliance_dimensions":["labor","foreign_investment","tax","environment","industry_access"],"missing_elements":["lab_workforce"],"note":"请补充用工计划"}' >/dev/null

SC=$(curl -sf "$API/scenarios/$SID" -H "Authorization: Bearer $BIZ")
REV_PAYLOAD=$(echo "$SC" | python3 -c "
import sys, json
s=json.load(sys.stdin)
print(json.dumps({
  'project_name': s['project_name'],
  'country': s['country'], 'state': s['state'], 'city': s['city'],
  'industry': s['industry'], 'action_type': s['action_type'],
  'investment_structure': s.get('investment_structure'),
  'description': s.get('description'),
  'employee_count': 480,
  'project_content_scale': s.get('project_content_scale'),
}, ensure_ascii=False))
")
curl -sf -X POST "$API/scenarios/$SID/revise-and-resubmit" \
  -H "Authorization: Bearer $BIZ" -H 'Content-Type: application/json' \
  -d "$REV_PAYLOAD" >/dev/null

INC=$(curl -sf -X POST "$API/scenarios/$SID/confirm-scope" \
  -H "Authorization: Bearer $LEGAL" -H 'Content-Type: application/json' \
  -d "{\"compliance_dimensions\":[\"labor\",\"foreign_investment\",\"tax\",\"environment\",\"industry_access\"],\"expected_proposal_hash\":\"$PROPOSAL_HASH\",\"fit_decision\":\"accept_warning\",\"polish\":false}")

echo "$INC" | python3 -c "
import sys, json
d=json.load(sys.stdin)
expected=sys.argv[1].split('|')
snapshot=d['scenario_scope']['snapshot']
actual=[snapshot['capability_pack_id'],snapshot['capability_pack_version'],snapshot['capability_pack_hash'],snapshot['rules_artifact_hash'],snapshot['corpus_artifact_hash']]
assert actual==expected, (actual, expected)
inc=d.get('incremental_regen') or {}
assert inc.get('mode')=='incremental', inc
assert 'lab_workforce' in (inc.get('target_elements') or []), inc
assert len(inc.get('target_codes') or [])>=1, inc
assert len(inc.get('frozen_codes') or [])>=1, inc
print('incremental ok:', 'target', len(inc['target_codes']), 'frozen', len(inc['frozen_codes']), 'changed', inc.get('changed_fields'))
" "$FIRST_PACK"

REV=$(curl -sf "$API/scenarios/$SID/review" -H "Authorization: Bearer $LEGAL")
echo "$REV" | python3 -c "
import sys, json
d=json.load(sys.stdin)
items={i['code']:i for i in d.get('items',[])}
assert items.get('FOR-001',{}).get('decision')=='approved', items.get('FOR-001')
assert items.get('FOR-001',{}).get('carry_forward') is True, items.get('FOR-001')
lab=items.get('LAB-001',{})
assert lab.get('decision') in ('pending','approved','rejected'), lab
print('review carry_forward FOR-001 ok; LAB-001 decision', lab.get('decision'))
"

echo "OK: incremental investigation verified"
