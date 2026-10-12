# 모델 직접 구현 검증

수집 결과는 **36개 모델 원본**, 설정 항목 **38개**입니다. 실제 원문·모델 ID·SHA-256이 일치합니다. Amazon Translate와 비활성 자체 배포 Gemma는 생성 불가로 표시합니다. `final-check.json`은 최초 수집 당시의 확인 기록이며, 이후 콘텐츠 재검수 결과와 구분해야 합니다.

배포 요청에 대한 최종 원본 검수는 **작품 32개 PASS / 4개 REVIEW**입니다. Llama 3.1 8B, Nova Micro, Nemotron Nano, EXAONE은 세 차례 재검수 이후에도 통과하지 못했습니다. 원래 모델의 응답과 시도 기록은 모두 보존합니다.

게시 제안안은 통과 작품 32개, 보류 안내 4개, 생성 불가 안내 2개, 목록으로 구성한 **39개 페이지 모두 PASS**입니다. 보류 작품과 미리보기 파일은 제안안에서 제외했습니다. `content-review-publication-proposal.json`과 상세 Markdown 보고서에 검사 결과가 있습니다. 사용자가 네 모델의 검수 보류 표시를 승인했습니다. 공개 대상은 이 검수된39개 페이지이며, `publication-plan.json`에 승인 및 게시 상태를 기록합니다. 최초 제안안 검수 보고서의 승인 대기 표시는 검수 당시의 기록입니다.

모델별 본문은 실제 모델 API 응답에서 얻었습니다. Codex가 직접 만든 이전 미디어아트 페이지·시·그래픽·생성 도구·미리보기는 삭제했습니다. 공통 목록, 작성 기록 표시줄, sandbox 뷰어와 실행·검증 도구만 Codex가 작성했습니다.

- `model-verification.json`: 2026-10-11 확인한 최신 Claude 4종과 OpenAI 2종의 공식 모델 카드, 가격 근거, 실제 호출 ID.
- `browser-check.json`: 각 원본 작품의 실제 Chromium 실행 결과, 화면에 표시된 글·버튼, Canvas 크기, 모바일 레이아웃과 오류.
- `feedback.json`: 발견된 문제를 같은 작성 모델에 전달하는 진단. 수정된 구현은 그 모델의 새 응답에서만 가져옵니다.
- `results/model-self-portraits/<name>/`: 요청문, 응답 원문, 실제 모델 식별자, 요청/응답 ID, 사용량과 생성 시각, 코드 SHA-256, 보존한 수정 시도.

원문 검증은 `artwork.html`의 바이트 SHA-256이 생성 기록과 일치하고, 그 코드 전체가 실제 응답 텍스트에 포함되며, 요청 모델 ID가 `config.toml`과 일치하는지 확인합니다. 임의로 구현 코드를 고치거나 다른 모델의 코드로 대체하지 않습니다.

브라우저는 offline으로 실행하고, 현재 작품과 공통 뷰어 파일만 파일 허용 목록으로 제공합니다. 모든 다른 파일·외부 네트워크·WebSocket 요청을 차단합니다. 작품을 sandbox/CSP로 격리한 뒤 다음을 확인합니다.

- 본문 iframe과 원본이 로드되는지, JavaScript 실행 오류가 없는지.
- 실제 포인터로 표시된 버튼을 클릭할 수 있는지.
- 1440×900 데스크톱과 390×844 모바일에서 가로 넘침 및 화면 밖 버튼이 없는지.
- 각 모델 원본을 실행한 실제 카드 미리보기.

검사 결과는 위 항목에 대한 것이며 모든 브라우저·접근성·애니메이션 성능을 인증하는 것은 아닙니다. 독립 콘텐츠 검수에서는 실제 재생·정지, 접근성, 모바일 배치까지 따로 확인합니다. 최초 `content-review-iteration-1.md`의 전체 판정은 REVIEW였으며 배포 승인이 아닙니다. 수정은 원래 작성 모델에게 요청하고 재검수합니다.

```sh
PLAYWRIGHT_MODULE=/path/to/playwright CHROMIUM_PATH=/path/to/chromium \
  node tools/check_self_portraits.cjs
# 수정한 특정 작품만 검사하고 기존 결과에 병합
PLAYWRIGHT_MODULE=/path/to/playwright CHROMIUM_PATH=/path/to/chromium \
  node tools/check_self_portraits.cjs nova-micro,exaone-3.5-32b
```

벤치마크의 기존 데이터와 보고서는 다시 생성하지 않았습니다. 최신 모델은 `config.toml`에서만 등록하며, 해당 모델의 필수 temperature 생략을 반영했습니다. 새 OpenAI 6 후보의 캐시 입력도 공식 Responses 사용량 규약에 따라 일반 입력·캐시 읽기·캐시 쓰기로 분리해 중복 과금을 방지합니다. 기존 Mantle/judge 모델의 역사적 집계는 바꾸지 않았습니다.

`bench.report --selfcheck` 및 `bench.run --selfcheck`가 통과했습니다. 새 캐시 과금 경로의 손계산은 `bench/report.py::_selfcheck()`에 있으며, 같은 가상 토큰 모집단에서 Astra **$15.62**, Sol **$3.102**를 단언합니다. 이는 검증용 모집단의 계산이며 이번 작품 생성 비용 총액이 아닙니다.

실제 자체 배포 후보는 `mall-apne2-mgmt`의 `llm-bench` 네임스페이스에서 `vllm-self-portrait` 임시 서버를 사용합니다. 기존 `gpu-bench` NodePool·taint·인스턴스 크기·8192 문맥 상한을 유지하고, 모델별 GPU/TP/eager/trust 설정은 `config.toml`에서 읽습니다. 각 설정은 `serving-config.json`으로 보관합니다. 다른 테넌트나 기존 NodePool 설정은 수정하지 않습니다.

GitHub Pages 게시 설정은 `main` 브랜치의 `/docs`입니다. 배포 요청에 따라 준비하고 있으며, AWS Content Plugin의 콘텐츠 리뷰 게이트를 통과한 게시 대상만 배포합니다. 실제 게시 여부와 최종 검수 결과는 배포 완료 기록으로 확인해야 합니다.
