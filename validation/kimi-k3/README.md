# Kimi K3 추가 검증

2026-09-20에 Bedrock 모델·프로파일 API, 공식 모델 카드 및 가격 API를 확인했다.
선택한 경로는 `bedrock-runtime`, 리전 `us-west-2`, US Geo 프로파일
`us.moonshotai.kimi-k3`다. Global 프로파일과 US 프로파일의 가격을 혼합하지 않는다.

공식 모델 카드:
`https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-moonshot-ai-kimi-k3.html`

US Standard 단가는 100만 토큰당 일반 입력 $3.30, 출력 $16.50,
캐시 읽기 $0.33, 캐시 쓰기(30분) $4.125다.
`pricing-us-standard.json`은 `model=Kimi K3`, `regionCode=us-west-2`,
`service_tier=standard` 필터로 조회한 AWS Price List 원본이다.
API의 `1K tokens` 단가를 1,000배 하여 `config.toml`에 기록했다.

실제 Converse 호출은 `temperature=0`을 거부했다. 해당 프로파일에만
temperature 생략 예외를 추가하고, 출력 상한4096과 기존 동시성은 유지한다.
추론은 제공자 기본값이며, 사전 호출에서 reasoningContent가 관측됐다.
Converse의 이전 추론 블록을 포함한 다중 턴·첨부 PDF 제한은 이 벤치마크의
단일 턴 일반 텍스트 호출에는 해당하지 않는다. 새로운 API 키를 만들지 않는다.

## 캐시 비용

`live-check.json`의 실제 반복 호출에서 다음 계수를 확인했다.

- 첫 요청: 일반 입력7 + 캐시 쓰기1694 + 출력36 = totalTokens1737.
- 재요청: 일반 입력7 + 캐시 읽기1694 + 출력90 = totalTokens1791.

따라서 `inputTokens`에 캐시 토큰이 포함됐다고 가정하면 안 된다.
원본 응답의 `cacheReadInputTokens`, `cacheWriteInputTokens`를 별도로 보존하고
모델 전체 비용에서 각 단가를 적용한다. 한 문항·언어쌍 단위 비용은 산출하지 않는다.
캐시 사용이 관측됐는데 단가가 없으면 잘못된 비용을 공개하지 않고 계산을 중단한다.

## 측정과 이력

번역은 보존된 `grok-explicit-2026-09-16/dataset.jsonl`의3,300개 입력과
현재 데이터가 전부 일치함을 확인했다. 기존 번역 프롬프트·두 평가자를 사용한다.
금융 QA는 감사된 기존20문항·프롬프트·채점기를 그대로 사용한다.
Kimi 추가 전 계약을 고정하고, 번역 데이터와 평가에 사용한 번역 원본 해시를 보존한다.

```bash
uv run python -m bench.kimi_benchmark selfcheck
uv run python -m bench.kimi_benchmark freeze
uv run python -m bench.kimi_benchmark run-qa
uv run python -m bench.kimi_benchmark run-translation
uv run python -m bench.kimi_benchmark judge-translation
uv run python -m bench.kimi_benchmark report-qa
uv run python -m bench.kimi_benchmark report-translation
```

기존 금융 QA의 `freeze.json`은 수정하지 않는다. 신규 모델을 지원하는 수집기와
캐시 비용 코드의 해시는 별도 추가 측정 계약에 기록한다. 이전28개 점수·비용을
그대로 유지하고, 신규1개만 합친다. 기존560개 판정의 재현과 변경 없는 채점기·
데이터 해시는 `verify-parent`로 확인한다. 이전 수집기까지 포함한 완전한
2026-09-19 재현은 원래 Git 커밋 `37fa864652504c0b35fe27831eddb56fae76356e`를
별도 체크아웃해 실행해야 한다. 현재 수집기를 이전 freeze로 위장하지 않는다.

번역의 공개 비교는 이전29개 스냅샷에 Kimi를 더한30개 모델이다.
금융 QA는 이전28개 스냅샷에 Kimi를 더한29개 모델이다.
이전 모델을 새로 측정한 결과처럼 표시하지 않으며, 측정 시점·요청 설정 차이를 명시한다.
