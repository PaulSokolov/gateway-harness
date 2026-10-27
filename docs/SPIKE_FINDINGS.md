# Spike Findings: LiteLLM Seams and Metadata Propagation (P0.3)

Date: 2026-10-26  
LiteLLM Version: `1.106.4`  

## 1. Was the model rewritten?
**YES.**
In `async_pre_call_hook`, changing `data["model"] = "spike-dst"` successfully redirected the proxy routing.
- The HTTP response returned `choices[0].message.content: "Hello from spike-dst"`.
- Response header confirmed: `x-litellm-model-group: spike-dst`.
- Standard logging payload confirmed:
  ```json
  "model": "openai/fake-dst",
  "model_group": "spike-dst"
  ```

## 2. Did custom response headers arrive?
**YES.**
Implemented via `async_post_call_response_headers_hook`:
```http
x-gh-optimized-from: spike-src
x-gh-policy: pol_test
```
Both non-streaming and streaming SSE requests received these headers intact.

## 3. Which path preserves `gh_policy_id`?
**Both `requester_metadata` and `request_tags` preserve custom values.**
In `async_pre_call_hook`:
1. Setting `data.setdefault("metadata", {})["requester_metadata"]["gh_policy_id"] = "pol_test"` survived into:
   ```json
   "metadata": {
     "requester_metadata": {
       "gh_policy_id": "pol_test"
     }
   }
   ```
2. Appending to tags (`data.setdefault("metadata", {})["tags"].append("gh:policy:pol_test")`) survived into top-level:
   ```json
   "request_tags": ["gh:policy:pol_test", "User-Agent: curl", "User-Agent: curl/8.7.1"]
   ```
**Decision for gateway_harness:** We set both `metadata.requester_metadata["gh_policy_id"]` and the tag `"gh:policy:<id>"` for dual redundancy.

## 4. Is the success event emitted once for streams, with full response text?
**YES.**
- For a streaming request (`"stream": true`), `async_log_success_event` fired **exactly once** after all chunks were delivered.
- The response object contained the fully assembled text:
  ```json
  "response": {
    "choices": [
      {
        "finish_reason": "stop",
        "index": 0,
        "message": {
          "content": "Hello from spike-dst",
          "role": "assistant"
        }
      }
    ]
  }
  ```
- `stream` flag was preserved: `"stream": true` and `"model_parameters": {"stream": true}`.

## 5. Where are `cached_tokens` and `session_id`?
- **`session_id`**: Located at the top-level of `StandardLoggingPayload`:
  `payload["session_id"]` (string, empty when not provided, or populated from header `x-litellm-session-id` / parameter `litellm_session_id`).
- **`cached_tokens`**: Located in:
  - `payload["metadata"]["usage_object"]["prompt_tokens_details"]["cached_tokens"]`
  - When reported by the provider, also at `payload.get("prompt_tokens_details", {}).get("cached_tokens")`.

## 6. What do key and team fields look like in `user_api_key_dict` and payload?
In `payload["metadata"]`:
```json
{
  "user_api_key_hash": "litellm_proxy_master_key",
  "user_api_key_alias": null,
  "user_api_key_team_id": null,
  "user_api_key_user_id": "default_user_id",
  "team_id": null,
  "team_alias": null
}
```
When called with a team virtual key:
- `tenant_id` resolves to `payload["metadata"]["user_api_key_team_id"]` or `payload["metadata"]["team_id"]`.
- When no team is set, `tenant_id` resolves to `f"key:{hash8}"` where `hash8` is the first 8 characters of `user_api_key_hash`.
