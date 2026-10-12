# 모델이 만든 자기표현

`config.toml`에 등록된 실제 모델에 자기표현 미디어아트 HTML을 구현하도록 요청한 결과입니다. 이전 Codex가 직접 제작한 모델별 작품·창작 시·그래픽·생성 도구는 삭제했습니다.

- 목록: `/models/`
- 모델별 뷰어: `/models/<model-name>/`
- 모델이 반환한 HTML: `/models/<model-name>/artwork.html`
- 작성자·응답 식별자·원문 해시: `/models/<model-name>/provenance.json`

작품의 HTML·CSS·JavaScript·시·시각적 표현은 해당 모델의 실제 응답입니다. 코드 펜스와 문서 바깥의 응답 포장만 제거하고 구현 코드는 수정하지 않습니다. 목록, 작성 기록 표시줄, sandbox 뷰어, 캡처·검증 도구는 Codex가 구현했습니다. 뷰어는 iframe의 크기가 정해진 다음 원본을 로드합니다.

기본 요청은 `tools/self_portrait_prompt.txt`로 공통입니다. 모델 이름과 실제 호출 ID만 바꿔 요청합니다. 일부 모델의 잘린 응답에는 출력 예산을 늘려 다시 요청했고, 브라우저에서 확인된 코드 오류는 같은 작성 모델에게 이전 응답과 함께 돌려보내 수정받았습니다. 따라서 이 결과는 동일 조건의 단일 시도 코딩 벤치마크나 품질 순위가 아닙니다.

개별 요청문·응답 텍스트·사용량·요청 ID·생성 시각·코드 해시는 `results/model-self-portraits/<name>/`에 저장됩니다. 수정 시도와 실패 응답은 가능한 범위에서 `attempts/`에 보존합니다. 독자적으로 코드를 수정하면 해당 파일은 기록된 모델 원문과 달라집니다.

```sh
# 구성된 관리형 엔드포인트에서 실제 생성. 추론 비용이 발생합니다.
uv run python tools/generate_self_portraits.py --managed --concurrency 4

# 모델 서버가 config.toml의 주소에서 준비된 뒤 해당 가중치를 검증하고 생성.
uv run python tools/generate_self_portraits.py --models qwen3.6-27b --concurrency 1

# 이미 받은 실제 응답으로 목록·작성 기록만 갱신. 모델 호출 없음.
uv run python tools/generate_self_portraits.py --catalog-only

# 로컬 보기
python3 -m http.server 8000 -d docs
```

생성된 성공 결과는 다시 호출하지 않습니다. `--feedback <JSON>`과 `--models <names>`를 같이 지정하면 그 작성 모델이 자기 코드를 수정합니다. `--max-output-tokens`는 별도 콘텐츠 생성 프로세스에만 적용하며, 번역 벤치마크의 기본 예산을 변경하지 않습니다. 자체 배포 모델은 `/v1/models`가 요청한 실제 HF ID를 반환해야 호출합니다.

`--temperature`는 자체 배포 작품 요청에만 쓰는 별도 샘플링 설정이며 각 요청 기록에 보관합니다. 번역 벤치마크의 고정 설정은 바꾸지 않습니다. `--catalog-only --publication-review <JSON>`은 독립 검수의 점수·경고 수·원본 해시를 확인하고, 일치하는 PASS가 없는 작품을 ‘검수 보류’로 표시합니다. 실제 게시용 파일을 준비할 때 보류 작품의 `artwork.html`과 `preview.jpg`도 제외해야 합니다.

현재 기록의 `temperature_sent=false`, `temperature=null`은 API가 해당 파라미터를 허용하지 않아 실제 요청에서 생략했다는 뜻입니다. 초기 보존 기록의 `temperature=0`은 도구의 목표 기본값이므로 전송 여부의 증명으로 사용하지 않습니다. 응답 원문과 보존한 시도는 그대로 두고 현재 기록과 공개 출처 정보에 실제 전송 여부를 구분했습니다.

브라우저 검증:

```sh
PLAYWRIGHT_MODULE=/path/to/playwright CHROMIUM_PATH=/path/to/chromium \
  node tools/check_self_portraits.cjs
```

검증 브라우저는 offline으로 실행하며, 작품과 공통 뷰어 파일만 허용 목록으로 제공합니다. 다른 파일·외부 네트워크·WebSocket 요청을 차단하고, 작품은 별도 sandbox/CSP 안에서 실행합니다. 검증 결과와 작성 모델에게 전달하는 진단은 `validation/self-portraits/`에 저장됩니다. 카드 미리보기는 모델 원본을 실행한 실제 캡처입니다.

Amazon Translate는 코드 생성용 LLM이 아니므로 작품 대신 해당 상태를 표시합니다. 비활성 자체 배포 Gemma는 기존 GPU 메모리 제약으로 호출하지 않습니다. 다른 모델이 대신 작성한 작품으로 채우지 않습니다.

최신 공개 Claude 계열(Haiku/Sonnet/Opus 5.5, Fable 5.1)과 OpenAI GPT-6 Astra·GPT-6.1 Sol의 식별자·가격은 2026-10-11 공식 자료와 실제 호출로 확인했습니다. 증빙은 `validation/self-portraits/model-verification.json`에 있습니다. 공개 배포는 별도 작업이며 배포 전 AWS Content Plugin의 콘텐츠 리뷰 게이트를 적용해야 합니다.
