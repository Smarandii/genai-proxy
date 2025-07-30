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

…
