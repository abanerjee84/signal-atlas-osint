# Calling a running local model

`scripts/ask_local_model.py` is a small Python client, using the existing `requests` dependency. It never starts, stops or reloads a server, downloads weights, or changes dashboard data.

Run it from the project directory with the installed Python environment. Replace `your-model-alias` and the address with the actual server configuration; the API base must include `/v1`.

## Native System One decisions

For a llama.cpp build and GGUF that support native decisions:

```powershell
.venv\Scripts\python.exe scripts/ask_local_model.py "The army announced a training exercise." --model your-model-alias --base-url http://127.0.0.1:8081/v1 --questions docs/local-model-questions.json
```

The supplied JSON file defines a military activity choice question. The script sends the report as `state` and the file as `questions` to `/v1/systemone`. It prints the returned decisions, probabilities and usage as JSON. Edit the question file for other choice, score or yes/no (`noul`) tasks.

Current llama.cpp documentation describes this endpoint and exposes native support through `GET /v1/models`, under each model's `architecture.output_modalities` containing `decisions`. A regular text model does not become a native decision model by using this endpoint. Older builds or incompatible models may return HTTP 404 or 501; the client reports this without silently switching to chat.

## Chat models

For a regular instruction model such as Qwen3.5-0.8B:

```powershell
.venv\Scripts\python.exe scripts/ask_local_model.py "Summarize this report in one sentence: The army announced a training exercise." --model your-model-alias --base-url http://127.0.0.1:8081/v1
```

This calls `/v1/chat/completions`, limits output to 256 tokens by default and requests disabled thinking through the chat template. `--max-tokens` and `--timeout` change the output limit and request timeout. A prompt of `-` reads report text from standard input. If your endpoint requires authentication, set `LOCAL_MODEL_API_KEY` in the process environment; the script does not read the project's `.env` automatically.

Python callers can import `ask_model()` for text or `system_one()` for typed decisions. The script is a connection utility, not an ingestion pipeline: it does not validate every decision value, establish source facts, or calibrate confidence. Check results against labelled reports before using them for dashboard enrichment.

For a model on another machine, use authenticated HTTPS or a private tunnel. An unsecured local address is appropriate only when the server is on the same machine.

Protocol reference: [llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md#typesafe-compatible-api-endpoints).
