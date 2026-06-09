#!/usr/bin/env bash
# Vela 端到端验收：巴西投资协查规则包 + 业务/法务分角色 + 法务反馈
set -euo pipefail

API="${VELA_API:-http://127.0.0.1:8000/api/v1}"
PASS=0
FAIL=0

log() { echo "==> $*"; }
ok() { PASS=$((PASS + 1)); echo "  OK: $*"; }
bad() { FAIL=$((FAIL + 1)); echo "  FAIL: $*" >&2; }

login() {
  local email=$1
  curl -sf -X POST "$API/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$email\",\"password\":\"Demo1234!\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

auth_header() {
  echo "Authorization: Bearer $1"
}

log "1. Health"
curl -sf "$API/health" >/dev/null && ok "health" || bad "health"

log "2. Rules catalog (Brazil investment pack v2.9)"
PACK=$(curl -sf "$API/rules/catalog" -H "$(auth_header "$(login legal@demo.vela)")")
echo "$PACK" | python3 -c "
import sys, json
d=json.load(sys.stdin)
assert d.get('pack',{}).get('id')=='brazil_new_energy', d
assert d.get('rules_pack_id')=='brazil_new_energy', d
assert d.get('scene_defaults',{}).get('country')=='brazil', d
assert len(d.get('dimensions', [])) == 6, d.get('dimensions')
print('pack:', d['pack'].get('name'), 'dims:', len(d['dimensions']))
" && ok "catalog pack" || bad "catalog pack"

log "2b. Rules classification tree"
CLASS=$(curl -sf "$API/rules/classification" -H "$(auth_header "$(login legal@demo.vela)")")
echo "$CLASS" | python3 -c "
import sys, json
d=json.load(sys.stdin)
assert d.get('default_pack_id')=='brazil_new_energy', d
assert d.get('regions')[0]['id']=='latin_america', d
assert d['regions'][0]['countries'][0]['default_pack_id']=='brazil_new_energy', d
print('regions:', len(d['regions']), 'packs:', len(d['packs']))
" && ok "classification" || bad "classification"

log "3. BYD checklist item count"
TOKEN=$(login legal@demo.vela)
SC=$(curl -sf -X POST "$API/scenarios/demo/byd-campinas" -H "$(auth_header "$TOKEN")")
SID=$(echo "$SC" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
TOTAL=$(echo "$SC" | python3 -c "import sys,json; c=json.load(sys.stdin).get('checklist'); print(c['total_items'] if c else 0)")
if [ "$TOTAL" -ge 20 ]; then ok "BYD items=$TOTAL"; else bad "BYD items=$TOTAL (expected >=20)"; fi

log "4. Solar-only scenario (shorter checklist)"
SOLAR=$(curl -sf -X POST "$API/scenarios" -H "$(auth_header "$TOKEN")" -H 'Content-Type: application/json' -d '{
  "project_name": "坎皮纳斯光伏组件厂（验收）",
  "country": "brazil", "state": "sao_paulo", "city": "campinas",
  "industry": "new_energy", "action_type": "greenfield_plant",
  "investment_structure": "100% 外资",
  "description": "计划在坎皮纳斯建设太阳能电池板组件工厂，年产光伏组件 500MW，不涉及客车或动力电池生产。",
  "employee_count": 80,
  "compliance_dimensions": ["labor","foreign_investment","tax","environment","industry_access"]
}')
SOLAR_TOTAL=$(echo "$SOLAR" | python3 -c "import sys,json; print(json.load(sys.stdin)['checklist']['total_items'])")
if [ "$SOLAR_TOTAL" -lt "$TOTAL" ]; then ok "solar-only=$SOLAR_TOTAL < byd=$TOTAL"; else bad "solar-only=$SOLAR_TOTAL not shorter than byd=$TOTAL"; fi

log "5. Business submit materials + legal confirm scope + reject feedback"
BIZ=$(login biz@demo.vela)
SUB=$(curl -sf -X POST "$API/scenarios/demo/submit-materials" -H "$(auth_header "$BIZ")")
SUB_ID=$(echo "$SUB" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "$SUB" | python3 -c "
import sys, json
d=json.load(sys.stdin)
assert d.get('status')=='pending_scope', d
print('status:', d['status'])
" && ok "business submit materials" || bad "business submit materials"
LEGAL=$(login legal@demo.vela)
SCOPE=$(curl -sf -X POST "$API/scenarios/$SUB_ID/confirm-scope" \
  -H "$(auth_header "$LEGAL")" -H 'Content-Type: application/json' \
  -d '{"compliance_dimensions":["labor","foreign_investment","tax","environment","industry_access"],"polish":false}')
echo "$SCOPE" | python3 -c "
import sys, json
d=json.load(sys.stdin)
assert d.get('status')=='pending_legal_review', d
assert d.get('checklist',{}).get('total_items',0)>=20, d
print('items:', d['checklist']['total_items'])
" && ok "legal confirm scope" || bad "legal confirm scope"
curl -sf -X POST "$API/scenarios/$SUB_ID/review/init" -H "$(auth_header "$LEGAL")" >/dev/null
curl -sf -X PATCH "$API/scenarios/$SUB_ID/review/items/LAB-001" \
  -H "$(auth_header "$LEGAL")" -H 'Content-Type: application/json' \
  -d '{"decision":"rejected","comment":"雇员规模描述与现场调研不一致，请补充用工计划。"}' >/dev/null
BF=$(curl -sf "$API/scenarios/$SUB_ID" -H "$(auth_header "$BIZ")")
echo "$BF" | python3 -c "
import sys, json
d=json.load(sys.stdin)
bf=d.get('business_feedback')
assert bf, 'missing business_feedback'
assert bf['rejected_count']>=1, bf
assert any(i.get('comment') for i in bf.get('items',[])), bf
print('summary:', bf['summary'][:60])
" && ok "business_feedback" || bad "business_feedback"

log "6. Mining template returns 501"
CODE=$(curl -s -o /dev/null -w '%{http_code}' "$API/rules/demo-template/mining" -H "$(auth_header "$LEGAL")")
[ "$CODE" = "501" ] && ok "mining 501" || bad "mining status=$CODE"

log "7. Document extract (rules mode)"
EXTRACT=$(curl -sf -X POST "$API/scenarios/extract-document" \
  -H "$(auth_header "$TOKEN")" \
  -F "file=@scripts/fixtures/sample_storage_project.txt")
echo "$EXTRACT" | python3 -c "
import sys, json
d=json.load(sys.stdin)
assert d.get('employee_count')==120, d
assert '储能' in (d.get('description') or ''), d
assert d.get('mode') in ('rules','llm'), d
print('mode:', d['mode'], 'employees:', d['employee_count'])
" && ok "document extract" || bad "document extract"

log "7b. Document extract PDF"
PDF_FIXTURE="BYD坎皮纳斯_投资方案_演示.pdf"
if [ -f "$PDF_FIXTURE" ]; then
  EXTRACT_PDF=$(curl -sf -X POST "$API/scenarios/extract-document" \
    -H "$(auth_header "$TOKEN")" \
    -F "file=@$PDF_FIXTURE")
  echo "$EXTRACT_PDF" | python3 -c "
import sys, json
d=json.load(sys.stdin)
assert d.get('employee_count')==450, d
assert '坎皮纳斯' in (d.get('project_name') or d.get('description') or ''), d
assert d.get('mode') in ('rules','llm'), d
print('mode:', d['mode'], 'employees:', d['employee_count'])
" && ok "document extract pdf" || bad "document extract pdf"
else
  echo "skip: $PDF_FIXTURE not found"
fi

log "7c. Batch document extract (multi-file merge)"
BATCH=$(curl -sf -X POST "$API/scenarios/extract-documents" \
  -H "$(auth_header "$TOKEN")" \
  -F "files=@scripts/fixtures/sample_storage_project.txt" \
  -F "files=@scripts/fixtures/sample_storage_project.txt")
echo "$BATCH" | python3 -c "
import sys, json
d=json.load(sys.stdin)
assert len(d.get('files', [])) == 2, d
assert d.get('merged', {}).get('employee_count') == 120, d
assert d['merged'].get('filename'), d
print('batch files:', len(d['files']), 'merged:', d['merged']['filename'][:40])
" && ok "batch document extract" || bad "batch document extract"

log "8. Storage-only checklist shorter than BYD"
STOR=$(curl -sf -X POST "$API/scenarios" -H "$(auth_header "$TOKEN")" -H 'Content-Type: application/json' -d '{
  "project_name": "坎皮纳斯储能系统组装厂",
  "country": "brazil", "state": "sao_paulo", "city": "campinas",
  "industry": "new_energy", "action_type": "greenfield_plant",
  "investment_structure": "100% 外资",
  "description": "计划在坎皮纳斯建设工业级储能系统组装工厂，不涉及电动客车制造。约120名本地雇员，首年200MWh产能，厂房12000平方米。",
  "employee_count": 120,
  "compliance_dimensions": ["labor","foreign_investment","tax","environment","industry_access"]
}')
STOR_TOTAL=$(echo "$STOR" | python3 -c "import sys,json; print(json.load(sys.stdin)['checklist']['total_items'])")
if [ "$STOR_TOTAL" -lt "$TOTAL" ]; then ok "storage-only=$STOR_TOTAL < byd=$TOTAL"; else bad "storage=$STOR_TOTAL"; fi

log "9. Return to business + revise resubmit"
curl -sf -X POST "$API/scenarios/$SUB_ID/review/return-to-business" \
  -H "$(auth_header "$LEGAL")" -H 'Content-Type: application/json' \
  -d '{"note":"请补充雇员规模与用工计划说明"}' >/dev/null
RET_CHECK=$(curl -sf "$API/scenarios/$SUB_ID" -H "$(auth_header "$BIZ")")
echo "$RET_CHECK" | python3 -c "
import sys, json
d=json.load(sys.stdin)
assert d.get('status')=='returned_for_revision', d
assert d.get('can_revise') is True, d
bf=d.get('business_feedback') or {}
assert bf.get('is_returned'), bf
print('returned ok')
" && ok "return to business" || bad "return to business"

REV_PAYLOAD=$(echo "$RET_CHECK" | python3 -c "
import sys, json
s=json.load(sys.stdin)
s['description']=s['description']+' 已补充：本地用工将分三期招聘，首批150人。'
print(json.dumps({
  'project_name': s['project_name'],
  'country': s['country'], 'state': s['state'], 'city': s['city'],
  'industry': s['industry'], 'action_type': s['action_type'],
  'investment_structure': s.get('investment_structure'),
  'description': s['description'],
  'employee_count': s.get('employee_count'),
}, ensure_ascii=False))
")
REV=$(curl -sf -X POST "$API/scenarios/$SUB_ID/revise-and-resubmit" \
  -H "$(auth_header "$BIZ")" -H 'Content-Type: application/json' \
  -d "$REV_PAYLOAD")
echo "$REV" | python3 -c "
import sys, json
d=json.load(sys.stdin)
assert d.get('status')=='pending_scope', d
assert (d.get('revision_round') or 0)>=1, d
print('revision_round:', d.get('revision_round'))
" && ok "revise resubmit" || bad "revise resubmit"

echo ""
echo "Passed: $PASS  Failed: $FAIL"
[ "$FAIL" -eq 0 ]
