# OCR — automatic extraction from uploaded documents

OCR is a convenience (PROMPT.md §21): it **suggests** values that the doctor confirms. It never
saves anything, runs only on the server, and can be switched off without a code change.

## Flow

1. The document is uploaded first (`POST /api/v1/applications/{id}/documents/`), validated by
   content sniffing and image decoding, and stored in the private Blob container.
2. The SPA calls `POST /api/v1/documents/{id}/extract/` (button `مسح تلقائي`, shown only when the
   reference data says `ocr_enabled`).
3. Django checks the session, CSRF, object ownership and the per-user rate limit
   (`OCR_RATE_LIMIT`, default `30/hour`), reads the blob with the managed identity, and sends the
   image to the configured provider (`apps/ocr/services.py::extract_document`).
4. The raw fields are normalized (`apps/ocr/normalizers.py`: Eastern Arabic digits, 14-digit
   national ID, birth year from the ID, registration year from dates, triple names, governorate
   and enum mapping) and returned. The SPA merges them into **empty** fields only.
5. An `OCR_REQUESTED` audit entry records the document, the provider and the *names* of the
   suggested fields — never their values.

PDFs are not sent: the service answers `OCR_UNAVAILABLE` with
`المسح التلقائي غير متاح لملفات PDF، يرجى إدخال البيانات يدوياً` (§21.2 allows skipping PDFs with a
clear message; PDF uploads are themselves off by default, `ALLOW_PDF_DOCUMENTS=false`).

## Providers

| `OCR_PROVIDER` | Where | Behaviour |
|---|---|---|
| `mock` | development, tests | `apps/ocr/providers/mock.py`: deterministic raw values (Eastern digits, colloquial spellings) so the normalizers are exercised. Refused by production settings when OCR is enabled. |
| `azure_openai` | production | `apps/ocr/providers/azure_openai.py` (below). |

### Azure OpenAI provider

- **Model:** a vision-capable chat deployment (`AZURE_OPENAI_DEPLOYMENT`) on an Azure OpenAI
  resource (`AZURE_OPENAI_ENDPOINT`), API version `AZURE_OPENAI_API_VERSION` (must support
  structured outputs — `2024-08-01-preview` or later GA versions such as `2024-10-21`). Check the
  model's regional availability before choosing the region (see *Privacy* below).
- **Authentication:** the Container App's managed identity through
  `azure.identity.get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")`.
  The identity needs the **Cognitive Services OpenAI User** role on the resource. No API key exists
  in configuration; disable key auth on the resource (`disableLocalAuth`, Session 8 Bicep).
- **Request:** one `chat.completions.create` call per document:
  - system message = general Arabic instructions + the document-specific Arabic prompt ported
    from the prototype (`apps/ocr/schemas.py`; §21.3 fields per document type);
  - user message = a short Arabic instruction + the image as a `data:` URL (`detail: high`);
  - `response_format = {"type": "json_schema", "json_schema": <strict schema>}` — every field
    is a required string, no additional properties (structured outputs, no free-text parsing);
  - `max_completion_tokens=1000`, `store=False`, timeout 30 s, one SDK retry.
- **Answer handling:** a refusal, a non-`stop` finish reason (e.g. `length`, `content_filter`),
  invalid JSON or a non-object all become `OcrProviderError`; only the schema's string fields
  are kept.
- **Errors:** every SDK/network/credential error (`openai.*`, `httpx2.*`, `azure.identity`) is
  converted to `OcrProviderError` with a fixed message and **no chained exception** (SDK errors
  can echo request or response content). The service logs only the exception type and answers
  `503 OCR_UNAVAILABLE` with the generic Arabic message.

| Document | Prompt / schema (`apps/ocr/schemas.py`) | Suggested fields |
|---|---|---|
| `NATIONAL_ID_FRONT` | `national_id_front` | `member_name`, `national_id`, `birth_year` (from the ID), `governorate`, `neighborhood`, `address` |
| `NATIONAL_ID_BACK` | `national_id_back` | `gender`, `religion` |
| `SYNDICATE_ID` | `syndicate_id` | `registration_number`, `sub_syndicate`, `syndicate_registration_year`, `syndicate_type` |
| `BENEFICIARY_NATIONAL_ID`, `BIRTH_CERTIFICATE` | `beneficiary_document` | `name` (first three names), `national_id`, `birth_year` |

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `OCR_ENABLED` | `false` (production), `true` (development) | Off ⇒ no button, endpoint answers `OCR_UNAVAILABLE`. |
| `OCR_PROVIDER` | `mock` | `azure_openai` in production; `mock` is refused there. |
| `OCR_RATE_LIMIT` | `30/hour` | DRF scoped throttle per user (shared cache needed across replicas, Q-T6). |
| `AZURE_OPENAI_ENDPOINT` / `_DEPLOYMENT` / `_API_VERSION` | — | All three required by production settings when OCR is enabled with `azure_openai`. |
| `AZURE_CLIENT_ID` | — | Client id of the user-assigned managed identity. |

## Privacy

- **Nothing is logged:** not the image, not the prompt, not the answer, not extracted values.
  `apps/ocr/tests/test_azure_openai.py::test_no_logging_of_payload` captures every logger at
  DEBUG (including `openai`, `httpx2`, `azure`) and asserts no national ID, name, address or
  image bytes appear. The national-ID masking filter and the telemetry processors are a second
  line of defence.
- **What is sent:** the image of one identity document (national ID front/back, syndicate card,
  beneficiary ID or birth certificate) and fixed Arabic instructions containing no personal data,
  to the Azure OpenAI resource configured in `AZURE_OPENAI_ENDPOINT`.
- **Retention / abuse monitoring:** per Microsoft's published *Data, privacy and security for
  Azure OpenAI* documentation, prompts and outputs are not used to train models and are not
  shared with OpenAI, but **abuse monitoring may retain prompts (including images) and outputs
  for up to 30 days** for review, unless the organization is approved for modified abuse
  monitoring. `store=False` only disables the optional stored-completions feature. Re-check the
  current documentation before go-live; this is not legal advice.
- **Region:** choose a *Standard* (regional) or *Data Zone* deployment in the approved geography;
  a *Global* deployment may process data in any Azure region.
- **Legal approval:** sending identity documents to an AI service is a data-processing decision
  that requires legal approval before production use (business question 11, `docs/security.md`).
  Until then production keeps `OCR_ENABLED=false`.

## Verification status

- Unit tests run the real `openai.AzureOpenAI` client against an in-process mock transport and
  assert the exact HTTP request (path, `api-version`, `Authorization: Bearer`, no `api-key`,
  JSON-schema `response_format`, prompt, `data:` URL, `store=false`, timeout) and every error
  mapping.
- **NOT VERIFIED — requires Azure credentials:** a call to a real Azure OpenAI deployment, the
  managed-identity token, the role assignment, the model's quality on Egyptian documents, and
  content-filter behaviour on identity documents.
