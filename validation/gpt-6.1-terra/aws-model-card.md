AWS Documentation from https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-6-1-terra.html:

# GPT-6.1 Terra

## OpenAI logo. OpenAI — GPT-6.1 Terra

## Model Details

As the newest model in the Terra line, GPT-6.1 Terra combines detailed visual reasoning, accurate computer use, and improved factuality and natural writing over GPT-5.6 Terra for complex workflows. In OpenAI's Agents' Last Exam evaluation, it scored 15 percentage points higher than GPT-5.6 Terra, performed on par with GPT-6 Astra, and completed tasks more than three times faster than GPT-6 Astra and GPT-6.1 Sol. GPT-6.1 Terra offers balanced performance with input and output token prices at least 50% lower than those of GPT-6.1 Sol and GPT-5.6 Terra. For more information about model development and performance, see the [model/service card](https://deploymentsafety.openai.com/gpt-6-1-terra).

* **Model launch date:** October 26, 2026
* **EOL no sooner than:** October 26, 2027
* **Legacy period:** at least 6 months
* **Model lifecycle policy:** [Model lifecycle (For Models Launched Prior to Sept 7 2026)](./model-lifecycle-legacy.html)
* **Model EOL date:** N/A
* **End User License Agreements and Terms of Use:** [View](https://aws.amazon.com/legal/bedrock/third-party-models/)
* **Model lifecycle:** Active
* **Context window:** 1,050,000 tokens
* **Max output tokens:** 128,000
* **Marketplace product ID:** `prod-xynumvnbsn34g`

| **Input Modalities** | **Output Modalities** |
| --- | --- |
| Red circle with white X icon indicating error, cancel, or close action. Audio | Red circle with white X icon indicating error, cancel, or close action. Embedding |
| Green circle with white checkmark icon. Image | Red circle with white X icon indicating error, cancel, or close action. Image |
| Red circle with white X icon indicating error, cancel, or close action. Speech | Red circle with white X icon indicating error, cancel, or close action. Speech |
| Green circle with white checkmark icon. Text | Green circle with white checkmark icon. Text |
| Red circle with white X icon indicating error, cancel, or close action. Video | Red circle with white X icon indicating error, cancel, or close action. Video |

## Endpoints and APIs supported

The following tables show which endpoints and APIs are supported for GPT-6.1 Terra. For more information, see [APIs supported by Amazon Bedrock](./apis.html) and [Inference endpoints supported by Amazon Bedrock](./endpoints.html).

**Endpoint support**

| **Endpoint** | **Supported** |
| --- | --- |
| `bedrock-runtime` | supported |
| `bedrock-mantle` | supported |

**APIs supported on `bedrock-runtime` endpoint**

| **Messages** | **Responses** | **Chat Completions** | **Converse** | **Invoke** |
| --- | --- | --- | --- | --- |
| not-supported | supported | supported | supported | supported |

**APIs supported on `bedrock-mantle` endpoint**

| **Messages** | **Responses** | **Chat Completions** | **Converse** | **Invoke** |
| --- | --- | --- | --- | --- |
| not-supported | supported | supported | not-supported | not-supported |

###### Note

On `bedrock-mantle`, both APIs use the `/openai/v1` base path, not `/v1`. Use either API with this model:

* For Responses, use `/openai/v1/responses`.
* For Chat Completions, use `/openai/v1/chat/completions`.

###### Tip

Whenever possible, we recommend using the `bedrock-runtime` endpoint for new applications. See [Inference endpoints supported by Amazon Bedrock](./endpoints.html) for details.

## Capabilities and Features

**Bedrock Features**

**Features supported using `bedrock-runtime` endpoint**

| **Supported** | **Not Supported** |
| --- | --- |
| * Green circle with white checkmark icon. [Projects (default project only)](projects.html) * Green circle with white checkmark icon. [Invocation logs](model-invocation-logging.html) * Green circle with white checkmark icon. [Response streaming](/bedrock/latest/APIReference/API_runtime_InvokeModelWithResponseStream.html) * Green circle with white checkmark icon. [Abuse detection](abuse-detection.html) * Green circle with white checkmark icon. [Guardrails](guardrails.html) ([Converse API](conversation-inference.html) only) * Green circle with white checkmark icon. [Application inference profiles](cost-mgmt-application-inference-profiles.html) ([Converse API](conversation-inference.html) only; not supported with Responses or Chat Completions APIs) * Green circle with white checkmark icon. [Implicit Prompt Caching](prompt-caching.html#prompt-caching-implicit) (Responses, Chat Completions, InvokeModel, and Converse APIs) * Green circle with white checkmark icon. [Explicit Prompt Caching](prompt-caching.html#prompt-caching-explicit) (Responses API only) * supported [Structured outputs (JSON Schema; see API configuration)](#model-card-openai-gpt-6-1-terra-structured-output) * supported [Reasoning Summaries](https://developers.openai.com/api/docs/guides/reasoning#reasoning-summaries) (Responses, [Converse](conversation-inference.html), and ConverseStream APIs; on Converse, set `additionalModelRequestFields.reasoning.summary`) | * Red circle with white X icon indicating error, cancel, or close action. [Server-side tool use](tool-use.html) * Red circle with white X icon indicating error, cancel, or close action. [Intelligent prompt routing](prompt-routing.html) * Red circle with white X icon indicating error, cancel, or close action. [Count tokens](count-tokens.html) |

**Features supported using `bedrock-mantle` endpoint**

| **Supported** | **Not Supported** |
| --- | --- |
| * Green circle with white checkmark icon. [Server-side tool calling](tool-use.html) * Green circle with white checkmark icon. [Projects](projects.html) * Green circle with white checkmark icon. [Implicit Prompt Caching](prompt-caching.html#prompt-caching-implicit) (Responses API only) * Green circle with white checkmark icon. [Explicit Prompt Caching](prompt-caching.html#prompt-caching-explicit) (Responses API only) * supported [Reasoning Summaries](https://developers.openai.com/api/docs/guides/reasoning#reasoning-summaries) (Responses API only) | * Red circle with white X icon indicating error, cancel, or close action. [Application inference profiles](cost-mgmt-application-inference-profiles.html) (Responses and Chat Completions APIs only) |

### JSON Schema output on bedrock-runtime

Use JSON Schema to set the format of the model response. These settings apply to non-streaming calls on the `bedrock-runtime` endpoint. Choose a profile ID from [Programmatic access](#model-card-openai-gpt-6-1-terra-programmatic-access).

* For Chat Completions, set `response_format.type` to `json_schema`. Put `name`, `schema`, and `strict: true` in `response_format.json_schema`.
* For Responses, set `text.format.type` to `json_schema`. Put `name`, `schema`, and `strict: true` in `text.format`.
* For Converse, set `outputConfig.textFormat.type` to `json_schema`. In `outputConfig.textFormat.structure.jsonSchema`, set `name` and `schema`. Encode the schema as a JSON string. Then set `additionalModelRequestFields.text.format.strict` to `true`.

Use an object schema. Put all fields in `required`. Set `additionalProperties` to `false`. Validate your schema before you send it. Check for refusals or incomplete responses before you parse the output.

###### Important

For JSON Schema output with the Converse API, you must set `additionalModelRequestFields.text.format.strict` to `true`, in addition to specifying the schema in `outputConfig`. Include the following field in your request.

```
{
  "additionalModelRequestFields": {
    "text": {
      "format": { "strict": true }
    }
  }
}
```

**Converse content blocks**

On the `bedrock-runtime` endpoint, Converse accepts `text` and
`image` content blocks in user messages. This model doesn't accept
`document` content blocks, and it doesn't accept an `image` content block
inside a `toolResult`. A request that includes either is rejected with a
`ValidationException`. To send a document to this model, use the Responses API with
an `input_file` content part instead.

## Pricing

All prices are in USD per 1 million tokens for the Standard tier.

The **Input — 30-minute cache write** column is the price per 1 million tokens written to the prompt cache. The 30-minute figure is how long a cached prompt prefix is retained, not a quantity of tokens. For more information, see [prompt caching](./prompt-caching.html).

Commercial In-Region prices include a 10% fee over OpenAI rates. You do not need to add this fee.

*Priority and Flex tiers are not supported for this model.*

### Commercial Regions — short context (272K input tokens or fewer)

| **Inference option** | **Input** | **Input — 30-minute cache write** | **Input — cache read** | **Output** |
| --- | --- | --- | --- | --- |
| In-Region | $1.10 | $1.375 | $0.055 | $5.50 |
| Geo CRIS | $1.10 | $1.375 | $0.055 | $5.50 |
| Global CRIS | $1.00 | $1.25 | $0.05 | $5.00 |

### Commercial Regions — long context (more than 272K input tokens)

| **Inference option** | **Input** | **Input — 30-minute cache write** | **Input — cache read** | **Output** |
| --- | --- | --- | --- | --- |
| In-Region | $2.20 | $2.75 | $0.11 | $8.25 |
| Geo CRIS | $2.20 | $2.75 | $0.11 | $8.25 |
| Global CRIS | $2.00 | $2.50 | $0.10 | $7.50 |

## Programmatic Access

Use the following model IDs and endpoint URLs to access this model programmatically. For more information about the available APIs and endpoints, see [APIs supported](apis.html) and [Endpoints supported](endpoints.html).

| **Endpoint** | **Model ID** | **In-Region endpoint URL** | **Geo inference ID** | **Global inference ID** |
| --- | --- | --- | --- | --- |
| `bedrock-mantle` | `openai.gpt-6.1-terra` | `https://bedrock-mantle.{region}.api.aws/openai/v1` | Not supported | Not supported |
| `bedrock-runtime` | `openai.gpt-6.1-terra` | Not supported | `us.openai.gpt-6.1-terra` | `global.openai.gpt-6.1-terra` |

*For example, if region is us-east-1 (N. Virginia), then the bedrock-mantle endpoint URL will be "https://bedrock-mantle.us-east-1.api.aws/openai/v1". On `bedrock-runtime`, the base URL is "https://bedrock-runtime.{region}.amazonaws.com/openai/v1" and requests must name the geographic cross-Region inference ID `us.openai.gpt-6.1-terra` as the model.*

## Service Tiers

Amazon Bedrock offers multiple service tiers to match your workload requirements. **Standard** provides pay-per-token access with no commitment (set `"service_tier": "default"` or omit the field). **Priority** delivers the fastest response times for a price premium (set `"service_tier": "priority"`). **Flex** provides lower-cost access for flexible, non-time-sensitive workloads (set `"service_tier": "flex"`). **Reserved** provides dedicated throughput with a term commitment for predictable workloads; it is set at the account level rather than per request (contact your AWS account team to enable). For more information, see [service tiers](service-tiers-inference.html).

| **Standard** | **Priority** | **Flex** | **Reserved** |
| --- | --- | --- | --- |
| Green circle with white checkmark icon. | Red circle with white X icon indicating error, cancel, or close action. | Red circle with white X icon indicating error, cancel, or close action. | Red circle with white X icon indicating error, cancel, or close action. |

## Regional Availability

**Regional availability at a glance**

Amazon Bedrock offers three inference options: **In-Region** keeps requests within a single Region for strict compliance, **Geo Cross-Region** routes across Regions within a geography (such as US, EU, and APAC) while respecting data residency, and **Global Cross-Region** routes anywhere worldwide when there are no residency constraints. Refer to the [Regional availability by models](./models-region-compatibility.html) page for more details.

Availability differs by endpoint.

**Availability using the `bedrock-mantle` endpoint**

| **Region** | **In-Region** | **Geo** | **Global** |
| --- | --- | --- | --- |
| `us-east-1` (N. Virginia) | Green circle with white checkmark icon. | Red circle with white X icon indicating error, cancel, or close action. | Red circle with white X icon indicating error, cancel, or close action. |
| `us-east-2` (Ohio) | Red circle with white X icon indicating error, cancel, or close action. | Red circle with white X icon indicating error, cancel, or close action. | Red circle with white X icon indicating error, cancel, or close action. |
| `us-west-2` (Oregon) | Red circle with white X icon indicating error, cancel, or close action. | Red circle with white X icon indicating error, cancel, or close action. | Red circle with white X icon indicating error, cancel, or close action. |
| `us-gov-west-1` (GovCloud West) | Red circle with white X icon indicating error, cancel, or close action. | Red circle with white X icon indicating error, cancel, or close action. | Red circle with white X icon indicating error, cancel, or close action. |
| `us-gov-east-1` (GovCloud East) | Red circle with white X icon indicating error, cancel, or close action. | Red circle with white X icon indicating error, cancel, or close action. | Red circle with white X icon indicating error, cancel, or close action. |

**Availability using the `bedrock-runtime` endpoint**

| **Region** | **In-Region** | **Geo** | **Global** |
| --- | --- | --- | --- |
| `us-east-1` (N. Virginia) | Red circle with white X icon indicating error, cancel, or close action. | Green circle with white checkmark icon. | Green circle with white checkmark icon. |
| `us-east-2` (Ohio) | Red circle with white X icon indicating error, cancel, or close action. | Green circle with white checkmark icon. | Green circle with white checkmark icon. |
| `us-west-1` (N. California) | Red circle with white X icon indicating error, cancel, or close action. | Green circle with white checkmark icon. | Green circle with white checkmark icon. |
| `us-west-2` (Oregon) | Red circle with white X icon indicating error, cancel, or close action. | Green circle with white checkmark icon. | Green circle with white checkmark icon. |
| `ca-central-1` (Canada) | Red circle with white X icon indicating error, cancel, or close action. | Green circle with white checkmark icon. | Green circle with white checkmark icon. |


Table truncated (showing 5 of 32 rows). Use the `search_table` tool to find specific rows.
  Example: search_table(url="https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-6-1-terra.html", section_title="<section>", query="your search term")

**Geo inference details**

The destination Regions available to a geographic inference profile depend on the source Region. To retrieve the current routing configuration, call [GetInferenceProfile](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_GetInferenceProfile.html) from the source Region.

**Geo: US**

Geo inference ID: `us.openai.gpt-6.1-terra`

| **Source Region** | **Destination Regions** |
| --- | --- |
| us-east-1 (N. Virginia) | us-east-1 (N. Virginia), us-east-2 (Ohio), us-west-2 (Oregon) |
| us-east-2 (Ohio) | us-east-1 (N. Virginia), us-east-2 (Ohio), us-west-2 (Oregon) |
| us-west-1 (N. California) | us-east-1 (N. Virginia), us-east-2 (Ohio), us-west-1 (N. California), us-west-2 (Oregon) |
| us-west-2 (Oregon) | us-east-1 (N. Virginia), us-east-2 (Ohio), us-west-2 (Oregon) |
| ca-central-1 (Canada) | ca-central-1 (Canada), us-east-1 (N. Virginia), us-east-2 (Ohio), us-west-2 (Oregon) |
| ca-west-1 (Calgary) | ca-west-1 (Calgary), us-east-1 (N. Virginia), us-east-2 (Ohio), us-west-2 (Oregon) |

## Quotas and Limits

Your AWS account has default quotas to maintain the performance of the service and to ensure appropriate usage of Amazon Bedrock. The default quotas assigned to an account might be updated depending on regional factors, payment history, fraudulent usage, and/or approval of a quota [increase request](quotas-increase.html). For more information, see [Quotas for Amazon Bedrock](./quotas.html) documentation and see the [limits](/general/latest/gr/bedrock.html#limits_bedrock) for the model.

On Amazon Bedrock, each request can contain a maximum of 100 image inputs.

On the `bedrock-runtime` endpoint, limits are managed as tokens per minute (TPM) with a 10x burndown rate, where 1 output token consumes 10 tokens.

## Sample Code

**Step 1 - AWS Account:** If you have an AWS account already, skip this step. If you are new to AWS, sign up for an [AWS account](https://portal.aws.amazon.com/billing/signup).

**Step 2 - API key:** Go to the [Amazon Bedrock console](https://console.aws.amazon.com/bedrock/home#/api-keys/long-term/create) and generate a long-term API key.

**Step 3 - Get the SDK:** To use this getting started guide, you must have Python already installed. Then install the relevant software depending on the APIs you are using.

For both APIs, choose the OpenAI SDK tab.

OpenAI SDK
:   ```
    pip install openai
    ```

### Step 4 - Set environment variables

Configure your environment to use the API key for authentication.

bedrock-mantle
:   ```
    OPENAI_API_KEY="<provide your Bedrock API key>"
    OPENAI_BASE_URL="https://bedrock-mantle.us-east-1.api.aws/openai/v1"
    ```

###### Note

On `bedrock-runtime`, name a cross-Region inference profile as the model — `us.openai.gpt-6.1-terra` or `global.openai.gpt-6.1-terra`. This model is not available for in-Region inference on that endpoint. Your IAM identity also needs `bedrock:InvokeModel` on your account's default project (`arn:aws:bedrock:{region}:{account-id}:project/default`) in addition to the inference profile.

### Step 5 - Run your first inference request

Save the file as `bedrock-first-request.py`

#### bedrock-mantle

Use the settings from [Step 4 - Set environment variables](#model-card-openai-gpt-6-1-terra-sample-code-environment). Choose the `bedrock-mantle` tab. Send your request with the Responses API.

Responses API
:   ```
    from openai import OpenAI

    client = OpenAI()

    response = client.responses.create(
        model="openai.gpt-6.1-terra",
        input="Can you explain the features of Amazon Bedrock?"
    )
    print(response)
    ```

#### bedrock-runtime: OpenAI SDK

Use the settings from [Step 4 - Set environment variables](#model-card-openai-gpt-6-1-terra-sample-code-environment). Choose the `bedrock-runtime` tab. Send your request with the Responses API.

Responses API
:   ```
    from openai import OpenAI

    client = OpenAI()

    response = client.responses.create(
        model="us.openai.gpt-6.1-terra",
        input="Can you explain the features of Amazon Bedrock?"
    )
    print(response)
    ```
