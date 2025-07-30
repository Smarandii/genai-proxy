# AI API Proxy Service

This repository contains a simple proxy server implemented with FastAPI.
It forwards incoming HTTP requests to one of several AI service providers
(OpenAI, Gemini or Grok) based on the URL path prefix.

## Features

- Listens on any path of the form `/{provider}/...` where `provider` is
  `openai`, `gemini` or `grok`.
- Forwards the request method, headers, query parameters and body to the
  configured upstream provider.
- Injects an `Authorization: Bearer <API_KEY>` header if a key is provided and
  not already present in the request.
- Returns the upstream response directly, preserving status codes and
  response bodies.

## Build Locally:

```commandline
docker build -t olegsmarandi/genai-proxy:latest .
```

## Or fetch from docker hub and run:

```commandline
docker run --rm -p 8000:8000 -e OPENAI_BASE_URL=https://api.openai.com/v1 -e GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta -e GROK_BASE_URL=https://api.grok.com/v1 olegsmarandi/genai-proxy:latest
```
