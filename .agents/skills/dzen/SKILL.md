---
name: dzen
description: Publish or schedule approved materials on Dzen.ru, including local image attachments. Use the authorized channel editor, verify every upload, and confirm the public or scheduled result.
---

# Dzen Publisher

Use this skill for Dzen.ru publication tasks: an article with attachments, a test publication, or an approved delayed release. The project channel is `https://dzen.ru/profile/editor/ekonomikadliavseh` unless the user specifies another.

## Execution route

In this project, `dzen-publish/` is the primary and required transport for Dzen. Start every publication with `dzen-publish/ensure_cdp_chrome.ps1`, then run `publish_dzen.py --healthcheck` before opening a draft. The health check is read-only, bounded, and retries the CDP connection once. After it succeeds, use `publish_dzen.py` with `--media` and, for an approved delayed release, `--schedule YYYY-MM-DDTHH:MM`. Do not select Browser Use or Computer Use to create, upload, format, or schedule a Dzen article while this repository path is available. Those tools are only a recovery path after the script has produced a concrete, observed CDP/editor failure despite a successful health check.

## Publication route

1. Prepare one revision containing the title, body, local media files, channel, visibility, and intended publication time. Preserve approved text and files. Append exactly one copy of the [required Dzen footer](references/required-footer.md) after the body of every Dzen article, separated by a blank line. It must be the final visible article content; do not duplicate it if it is already present. For delayed publication, use `Europe/Moscow` unless the user gives another timezone, and leave at least one minute before the scheduled time.
2. Use the logged-in browser session. Session data, if needed by a local client, belongs only in `.local/auth/dzen_config.json`. Never ask the user to paste cookies or a CSRF token into chat, or write them to logs. If the browser is logged out or a session request returns `403`, stop for browser login and do not retry blindly.
3. Validate attachments before editing the draft. Supported images are `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, and `.gif`. A requested attachment remains part of the revision; do not silently publish a text-only substitute. For a DOCX with embedded images, run `tools/copy_docx_body_to_clipboard.ps1` and keep its rich clipboard intact until Dzen imports it. Build `tools/extract_docx_dzen_sequence.py` as an independent order manifest for verification and recovery.
4. In the channel editor, import a DOCX through `dzen-publish/publish_dzen.py --paste-docx <file> --expected-pasted-images <count> --footer-file <footer>`: Word pastes text and drawings together in source order. Never append or prepend all DOCX images as one batch. Use `--sequence <ordered.json>` only when rich paste is unavailable. Wait for `[data-testid="article-image-item"] img`; check the expected count, non-zero natural dimensions, and text context before and after every image before submission. The project’s verified local path is `dzen-publish/publish_dzen.py --media <image...> [--schedule YYYY-MM-DDTHH:MM]` through Chrome CDP at `http://localhost:9222`.
5. Before an external mutation, show the exact revision, channel, attachments, visibility, and publication time. Follow `AGENTS.md`: immediate public publication needs an explicit user request; a delayed release needs approval of this exact revision and schedule.
6. Submit once. For immediate publication leave **«Опубликовать позже»** unchecked. For a delayed release, select it, enter the approved date and time, and verify the displayed schedule before submission. A timeout before the editor opens triggers the bounded health-check recovery and does not by itself make the release `failed`. A timeout after draft mutation or an ambiguous response requires checking the existing draft or result before any submission retry.
7. Verify independently after submission: obtain the URL or scheduled status, then check title, body, channel, visibility/time, image count, and the required footer with its active links. Save evidence and per-platform state in `.tmp/publishing/<release-base>/` and `publish-log.md`. A local click alone is not proof of publication.

## Browser access

A browser connector reporting that access to the Dzen editor is blocked by its security policy does **not** prove that Dzen or the authenticated browser session is unavailable. It limits that connector only. Before returning such a blocker, read [the CDP recovery guide](references/cdp-recovery.md), run the safe CDP starter when the endpoint is absent, and complete the repository `--healthcheck`. Only report a blocked release after the health-check recovery, the local CDP publication path, and every available browser-control path have failed with observed, specific errors. A first CDP connection timeout must never be reported as the final blocker.

## Fallback

Do not assume the upstream `scripts/publish.py` exists or invent an undocumented Dzen API. The repository CDP script remains the default for both immediate and scheduled publication. Use Browser Use or Computer Use only after that script has failed despite a verified CDP session, and report the exact script failure if the fallback also fails.

For the project’s immediate editor path:

```powershell
python .\dzen-publish\publish_dzen.py .\article.txt --media .\assets\cover.png .\assets\photo.jpg --schedule 2026-09-24T14:00
```

Omit `--schedule` for immediate publication. A delayed release must still use the approved release workflow so its schedule is explicitly entered and verified.
