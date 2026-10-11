"""Call an already-running llama.cpp server; never launch or stop a server."""

import argparse
import json
import math
import os
import sys
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8081/v1"


def _post(endpoint, payload, base_url, timeout, api_key):
    headers = {"Authorization": "Bearer " + api_key} if api_key else {}
    response = requests.post(
        base_url.rstrip("/") + "/" + endpoint,
        headers=headers,
        json=payload,
        timeout=timeout,
        allow_redirects=False,
    )
    if response.status_code != 200:
        if endpoint == "systemone" and response.status_code in {404, 501}:
            raise ValueError("This server/model does not support native System One decisions")
        raise ValueError(f"Model server returned HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as error:
        raise ValueError("Model server returned invalid JSON") from error


def ask_model(prompt, model, base_url=BASE_URL, *, timeout=60, max_tokens=256, api_key=""):
    """Return chat text. It is unvalidated and must not establish facts."""
    result = _post(
        "chat/completions",
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        base_url,
        timeout,
        api_key,
    )
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("Model server returned an invalid completion") from error
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Model server returned an empty completion")
    return content.strip()


def system_one(state, questions, model, base_url=BASE_URL, *, timeout=60, api_key=""):
    """Return native typed decisions; model confidence still needs domain validation."""
    if not isinstance(questions, dict) or not questions:
        raise ValueError("Questions must be a nonempty JSON object")
    result = _post(
        "systemone",
        {"model": model, "state": state, "questions": questions},
        base_url,
        timeout,
        api_key,
    )
    answers = result.get("answers") if isinstance(result, dict) else None
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise ValueError("Model server returned missing or unexpected decisions")
    if not all(isinstance(answer, dict) for answer in answers.values()):
        raise ValueError("Model server returned invalid decisions")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", help="Prompt text, or '-' to read from standard input")
    parser.add_argument("--model", required=True, help="Model ID or alias configured on your server")
    parser.add_argument("--base-url", default=BASE_URL, help="Server API base, including /v1")
    parser.add_argument(
        "--questions", type=Path, help="JSON question file: use native /systemone instead of chat"
    )
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--max-tokens", type=int, default=256)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0 or args.max_tokens <= 0:
        parser.error("Timeout and max-tokens must be positive")
    prompt = sys.stdin.read() if args.prompt == "-" else args.prompt
    if not prompt.strip():
        parser.error("Prompt must not be empty")
    try:
        options = {"timeout": args.timeout, "api_key": os.environ.get("LOCAL_MODEL_API_KEY", "")}
        if args.questions:
            questions = json.loads(args.questions.read_text(encoding="utf-8-sig"))
            answer = json.dumps(
                system_one(prompt, questions, args.model, args.base_url, **options),
                ensure_ascii=False,
                indent=2,
            )
        else:
            answer = ask_model(prompt, args.model, args.base_url, max_tokens=args.max_tokens, **options)
    except requests.RequestException:
        print("Model request failed. Check the endpoint, network and timeout.", file=sys.stderr)
        return 1
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except OSError:
        print("Cannot read the questions file.", file=sys.stderr)
        return 1
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
