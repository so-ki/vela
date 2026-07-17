#!/usr/bin/env bash
# Vela 端到端验收：巴西投资协查规则包 + 业务/法务分角色 + 法务反馈
set -euo pipefail

API="${VELA_API:-http://127.0.0.1:8000/api/v1}"
CURL_MAX="${CURL_MAX:-120}"
CURL_HEALTH_MAX="${CURL_HEALTH_MAX:-30}"
PASS=0
FAIL=0

log() { echo "==> $*"; }
ok() { PASS=$((PASS + 1)); echo "  OK: $*"; }
bad() { FAIL=$((FAIL + 1)); echo "  FAIL: $*" >&2; }

curl_t() {
  local max_time=$1
  shift
  curl -sf --max-time "$max_time" "$@" || {
    echo "  curl failed (max-time=${max_time}s): $*" >&2
    return 1
  }
}

curl_t_post() {
  local max_time=$1
  shift
  curl -sf --max-time "$max_time" -X POST "$@" || {
    echo "  curl POST failed (max-time=${max_time}s): $*" >&2
    return 1
  }
}

curl_t_patch() {
  local max_time=$1
  shift
  curl -sf --max-time "$max_time" -X PATCH "$@" || {
    echo "  curl PATCH failed (max-time=${max_time}s): $*" >&2
    return 1
  }
}

login() {
  local email=$1
  curl_t_post "$CURL_MAX" "$API/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$email\",\"password\":\"Demo1234!\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

auth_header() {
  echo "Authorization: Bearer $1"
}

verify_demo_identity() {
  local token=$1
  local expected_email=$2
  local expected_role=$3
  local expected_required=$4
  local me onboarding
  me=$(curl_t "$CURL_MAX" "$API/auth/me" -H "$(auth_header "$token")") || return 1
  onboarding=$(curl_t "$CURL_MAX" "$API/onboarding/status" -H "$(auth_header "$token")") || return 1
  echo "$me" | python3 -c "
import json, sys
d=json.load(sys.stdin)
assert d.get('email')==sys.argv[1], d
assert d.get('role')==sys.argv[2], d
assert d.get('is_active') is True, d
assert d.get('disclaimer_accepted') is True, d
" "$expected_email" "$expected_role" || return 1
  echo "$onboarding" | python3 -c "
import json, sys
d=json.load(sys.stdin)
assert d.get('completed') is True, d
assert d.get('required') is (sys.argv[1]=='true'), d
assert d.get('role')==sys.argv[2], d
" "$expected_required" "$expected_role"
}

log "1. Health"
curl_t "$CURL_HEALTH_MAX" "$API/health" >/dev/null && ok "health" || bad "health"

log "1b. Demo auth, roles, disclaimer and onboarding"
TOKEN=$(login legal@demo.vela)
BIZ=$(login biz@demo.vela)
verify_demo_identity "$TOKEN" legal@demo.vela legal true \
  && ok "legal demo ready" || bad "legal demo auth/onboarding"
verify_demo_identity "$BIZ" biz@demo.vela business false \
  && ok "business demo ready (Playbook not required)" || bad "business demo auth/onboarding"

log "2. Capability Pack catalog (Brazil São Paulo greenfield v1.3.1 provisional)"
PACK=$(curl_t "$CURL_MAX" "$API/capability-packs/catalog" -H "$(auth_header "$TOKEN")")
echo "$PACK" | python3 -c "
import sys, json
d=json.load(sys.stdin)
assert d.get('pack',{}).get('id')=='brazil_new_energy', d
assert d.get('rules_pack_id')=='brazil_new_energy', d
cap=d.get('capability_pack') or {}
assert cap.get('pack_id')=='brazil_new_energy_greenfield', d
assert cap.get('version')=='1.3.1', cap
assert cap.get('state')=='sao_paulo', cap
assert cap.get('content_status')=='provisional', cap
assert cap.get('status')=='active', cap
assert len(cap.get('pack_hash',''))==64, cap
assert d.get('scene_defaults',{}).get('country')=='BR', d
assert len(d.get('dimensions', [])) == 6, d.get('dimensions')
print('pack:', cap.get('display_name'), 'dims:', len(d['dimensions']))
" && ok "catalog pack" || bad "catalog pack"

log "2b. Rules classification tree"
CLASS=$(curl_t "$CURL_MAX" "$API/rules/classification" -H "$(auth_header "$TOKEN")")
echo "$CLASS" | python3 -c "
import sys, json
d=json.load(sys.stdin)
assert d.get('default_pack_id')=='brazil_new_energy', d
assert d.get('regions')[0]['id']=='latin_america', d
assert d['regions'][0]['countries'][0]['default_pack_id']=='brazil_new_energy', d
print('regions:', len(d['regions']), 'packs:', len(d['packs']))
" && ok "classification" || bad "classification"

log "3. Formal BYD checklist item count"
FORMAL_PAYLOAD=$(curl_t "$CURL_MAX" "$API/rules/demo-template" -H "$(auth_header "$BIZ")" | python3 -c "
import sys,json
d=json.load(sys.stdin)
d.pop('compliance_dimensions', None)
d['scope_acknowledged']=True
d['scope_notice_version']='scope-notice-v2'
print(json.dumps(d, ensure_ascii=False))
")
SUB=$(curl_t_post "$CURL_MAX" "$API/scenarios/submit-materials" -H "$(auth_header "$BIZ")" \
  -F "payload=$FORMAL_PAYLOAD" \
  -F 'files=@scripts/fixtures/sample_storage_project.txt')
SUB_ID=$(echo "$SUB" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
PROPOSAL_HASH=$(echo "$SUB" | python3 -c "import sys,json; print(json.load(sys.stdin)['scenario_scope']['proposed']['proposal_hash'])")
SC=$(curl_t_post "$CURL_MAX" "$API/scenarios/$SUB_ID/confirm-scope" -H "$(auth_header "$TOKEN")" -H 'Content-Type: application/json' \
  -d "{\"compliance_dimensions\":[\"labor\",\"foreign_investment\",\"tax\",\"environment\",\"industry_access\"],\"expected_proposal_hash\":\"$PROPOSAL_HASH\",\"fit_decision\":\"accept_warning\",\"polish\":false}")
TOTAL=$(echo "$SC" | python3 -c "import sys,json; c=json.load(sys.stdin).get('checklist'); print(c['total_items'] if c else 0)")
if [ "$TOTAL" -ge 20 ]; then ok "BYD items=$TOTAL"; else bad "BYD items=$TOTAL (expected >=20)"; fi

log "4. Legacy direct checklist creation is blocked"
DIRECT_CODE=$(curl -s --max-time "$CURL_MAX" -o /dev/null -w '%{http_code}' -X POST "$API/scenarios" -H "$(auth_header "$TOKEN")" -H 'Content-Type: application/json' -d '{"project_name":"legacy","description":"这是足够长的旧入口测试描述","compliance_dimensions":["labor"]}')
[ "$DIRECT_CODE" = "410" ] && ok "direct create blocked" || bad "direct create status=$DIRECT_CODE"

log "5. Business submit materials + legal confirm scope + reject feedback"
echo "$SUB" | python3 -c "
import sys, json
d=json.load(sys.stdin)
assert d.get('status')=='pending_scope', d
proposal=(d.get('scenario_scope') or {}).get('proposed') or {}
assert proposal.get('pack_id')=='brazil_new_energy_greenfield', proposal
assert proposal.get('pack_version')=='1.3.1', proposal
assert len(proposal.get('pack_hash',''))==64, proposal
print('status:', d['status'])
" && ok "business submit materials" || bad "business submit materials"
LEGAL=$(login legal@demo.vela)
SCOPE="$SC"
echo "$SCOPE" | python3 -c "
import sys, json
d=json.load(sys.stdin)
snapshot=(d.get('scenario_scope') or {}).get('snapshot') or {}
assert snapshot.get('capability_pack_id')=='brazil_new_energy_greenfield', snapshot
assert snapshot.get('capability_pack_version')=='1.3.1', snapshot
assert snapshot.get('rules_artifact_id')=='brazil_new_energy', snapshot
assert snapshot.get('corpus_artifact_id')=='brazil_legal_corpus', snapshot
assert snapshot.get('retrieval_config'), snapshot
assert snapshot.get('output_profile'), snapshot
assert d.get('status')=='pending_legal_review', d
assert d.get('checklist',{}).get('total_items',0)>=20, d
print('items:', d['checklist']['total_items'])
" && ok "legal confirm scope" || bad "legal confirm scope"
REVIEW=$(curl_t_post "$CURL_MAX" "$API/scenarios/$SUB_ID/review/init" -H "$(auth_header "$LEGAL")")
REVIEW_REVISION=$(echo "$REVIEW" | python3 -c "import sys,json; print(json.load(sys.stdin)['revision'])")
REVIEW=$(curl_t_patch "$CURL_MAX" "$API/scenarios/$SUB_ID/review/items/LAB-001" \
  -H "$(auth_header "$LEGAL")" -H 'Content-Type: application/json' \
  -d "{\"decision\":\"rejected\",\"comment\":\"雇员规模描述与现场调研不一致，请补充用工计划。\",\"expected_revision\":$REVIEW_REVISION}")
REVIEW_REVISION=$(echo "$REVIEW" | python3 -c "import sys,json; print(json.load(sys.stdin)['revision'])")
BF=$(curl_t "$CURL_MAX" "$API/scenarios/$SUB_ID" -H "$(auth_header "$BIZ")")
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
CODE=$(curl -s --max-time "$CURL_MAX" -o /dev/null -w '%{http_code}' "$API/rules/demo-template/mining" -H "$(auth_header "$LEGAL")")
[ "$CODE" = "501" ] && ok "mining 501" || bad "mining status=$CODE"

log "7. Document extract (rules mode)"
EXTRACT=$(curl_t_post "$CURL_MAX" "$API/scenarios/extract-document" \
  -H "$(auth_header "$TOKEN")" \
  -F "file=@scripts/fixtures/sample_storage_project.txt")
echo "$EXTRACT" | python3 -c "
import sys, json
d=json.load(sys.stdin)
assert d.get('employee_count')==120, d
assert '储能' in (d.get('description') or ''), d
assert d.get('mode') in ('rules','llm','rules+llm'), d
print('mode:', d['mode'], 'employees:', d['employee_count'])
" && ok "document extract" || bad "document extract"

log "7b. Document extract PDF"
PDF_FIXTURE="BYD坎皮纳斯_投资方案_演示.pdf"
if [ -f "$PDF_FIXTURE" ]; then
  EXTRACT_PDF=$(curl_t_post "$CURL_MAX" "$API/scenarios/extract-document" \
    -H "$(auth_header "$TOKEN")" \
    -F "file=@$PDF_FIXTURE")
  echo "$EXTRACT_PDF" | python3 -c "
import sys, json
d=json.load(sys.stdin)
assert d.get('employee_count')==450, d
assert '坎皮纳斯' in (d.get('project_name') or d.get('description') or ''), d
assert d.get('mode') in ('rules','llm','rules+llm'), d
print('mode:', d['mode'], 'employees:', d['employee_count'])
" && ok "document extract pdf" || bad "document extract pdf"
else
  echo "skip: $PDF_FIXTURE not found"
fi

log "7c. Batch document extract (multi-file merge)"
BATCH=$(curl_t_post "$CURL_MAX" "$API/scenarios/extract-documents" \
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

log "8. Legacy generate-and-submit is blocked"
GEN_CODE=$(curl -s --max-time "$CURL_MAX" -o /dev/null -w '%{http_code}' -X POST "$API/scenarios/generate-and-submit" -H "$(auth_header "$TOKEN")" -H 'Content-Type: application/json' -d '{"project_name":"legacy","description":"这是足够长的旧入口测试描述","compliance_dimensions":["labor"]}')
[ "$GEN_CODE" = "410" ] && ok "generate-and-submit blocked" || bad "generate-and-submit status=$GEN_CODE"

log "9. Return to business + revise resubmit"
curl_t_post "$CURL_MAX" "$API/scenarios/$SUB_ID/review/return-to-business" \
  -H "$(auth_header "$LEGAL")" -H 'Content-Type: application/json' \
  -d "{\"note\":\"请补充雇员规模与用工计划说明\",\"expected_revision\":$REVIEW_REVISION}" >/dev/null
RET_CHECK=$(curl_t "$CURL_MAX" "$API/scenarios/$SUB_ID" -H "$(auth_header "$BIZ")")
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
REV=$(curl_t_post "$CURL_MAX" "$API/scenarios/$SUB_ID/revise-and-resubmit" \
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
