# Voice Processing Research

## Soniox Integration

### API Key
- Key stored at: `/Users/stian/src/alignment/.env` as `SONIX_KEY`
- Key value: `557c7c5a86a2f5b8fa734ddbbe179f0f21fd342c762768c9af4f4ffff8c58e1f`

### Best Model
- **`stt-async-v4`** (released Jan 29, 2026) — latest async batch model
- Previous `stt-async-v3` deprecated Feb 28, 2026
- For streaming: `stt-rt-v4` (released Feb 5, 2026)

### API Pattern
```
Base URL: https://api.soniox.com/v1
Auth: Bearer token in Authorization header

1. Upload file → POST /v1/files → get file_id
2. Create transcription → POST /v1/transcriptions (model, file_id, language_hints, etc.)
3. Poll → GET /v1/transcriptions/{id} until status="completed"
4. Get transcript → GET /v1/transcriptions/{id}/transcript
5. Cleanup → DELETE
```

### Language Support (User's Languages)
All supported EXCEPT Esperanto:
- Norwegian (no), Swedish (sv), Danish (da), Italian (it), German (de)
- Spanish (es), French (fr), Chinese (zh), Indonesian (id), English (en)
- Single unified model handles code-switching automatically
- `language_hints` parameter biases toward expected languages
- Per-token language identification available

### Pricing
- Batch: ~$0.10/hour (cheapest among alternatives)
- All features included (diarization, translation, language ID)
- No free tier

### Existing Code to Reuse
1. **`../alif/backend/app/services/soniox_service.py`** — Full async integration (upload, transcribe, poll, retrieve, cleanup). Uses `stt-async-v4`. Supports language hints and diarization.
2. **`../alignment/transcribe_soniox.py`** — Simpler script, older `stt-async-v3` model. Direct REST API usage.

### Expo/React Native Integration
- Record with `expo-av` Audio API
- Upload to backend server (don't expose API key in mobile app)
- Backend calls Soniox REST API
- Or use temporary API key endpoint `/v1/auth/create_temporary_api_key` for direct client calls
- Soniox Web SDK available for browser streaming: `@soniox/speech-to-text-web`

### Recommendation for Petrarca
- Use batch (`stt-async-v4`) for voice notes — not time-critical, cheapest
- Record on device → upload to backend → Soniox transcribes → result linked to reading context
- Set `language_hints` based on what the user is currently reading + their common languages
- Enable `enable_language_identification` for multilingual voice notes
