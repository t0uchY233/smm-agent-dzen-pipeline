# Telegram transport provenance

Source: https://github.com/chigwell/telegram-mcp
Pinned commit: `0246df8c3c99818d68f50e8591b2d3dda8363f81`.
License: Apache-2.0. The verbatim `LICENSE` has SHA-256
`c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`.
No NOTICE file existed at this commit; preserve applicable upstream notices when updating.

`tg_post.py` is a modified selection, not the MCP runtime. It imports only stdlib
and Telethon and never creates a client or connects on import. The release adapter
retains approval, channel verification, upload size limits, the one-minute deadline,
state persistence, reconciliation and blind-retry protection.

SHA-256 of the complete `tg_post.py`:
`d787c2b07ebc58906a9b0f62c8f5ad29b23dbc33d0b369468ba8e80a121c935a`.

## Extracted blocks

Paths and line ranges refer to the pinned upstream commit. Hashes below cover the
UTF-8 text returned by `ast.get_source_segment(source, function_node)` from upstream
(no trailing newline). All listed verbatim functions have exactly that source text
locally. The `is_chat_allowed` function text also matches, but is conservatively
labelled modified because its `get_marked_id` dependency is replaced by Telethon's
public `get_peer_id` alias (Telethon does not export `utils.get_marked_id`).

| Function | Upstream location | Classification | Upstream function SHA-256 |
| --- | --- | --- | --- |
| `parse_schedule_date` | `telegram_mcp/runtime.py:127-151` | verbatim | `6f82e3cc0e0cfeeadd6c9d15aa427020cfbe0b00565f8801805fc18f8b3dfeb4` |
| `_parse_allowed_chat_ids` | `telegram_mcp/runtime.py:1158-1207` | verbatim | `e6e103cfe612d8df0ed175705617b6ae346979a66da5553d4ee6285d53d62d92` |
| `is_chat_allowed` | `telegram_mcp/runtime.py:1232-1271` | modified: get_marked_id resolves to telethon.utils.get_peer_id | `7b336e4f5b5b773b5ed5720bd54b7c97b22265f7626dc377f64ed3307177328e` |
| `check_chat_access` | `telegram_mcp/runtime.py:1274-1281` | verbatim | `813d294252047cb7d75c981ca63d34d46c5a71638be573f0ad4eba1a565c3fee` |
| `_is_flood_wait` | `telegram_mcp/runtime.py:1304-1309` | verbatim | `d19d2bdda74dc19414376163bbb1036ea074a3a8421c1462d437bc8034c1e557` |
| `_video_send_attributes` | `telegram_mcp/tools/media.py:48-58` | verbatim | `6bd63679a156b5f971cbbca6c5bfcb58976c51c878ce82657cdd219137154e48` |
| `_mp4_video_attributes` | `telegram_mcp/tools/media.py:61-77` | verbatim | `85cebed8603b7082253564d4bb4386d7959f525a5a8639661daaf44783d317a8` |
| `_find_box` | `telegram_mcp/tools/media.py:80-103` | verbatim | `1f150d69311e51db224aa39e97b8c53dec6636139a7c00840dc519bfc7c6301e` |
| `_parse_moov` | `telegram_mcp/tools/media.py:106-132` | verbatim | `c0cefc2f39213268bf0b1c38ffd50e0c573ad87bef4b1f3255b706564868f804` |
| `_parse_mvhd` | `telegram_mcp/tools/media.py:135-146` | verbatim | `166e2940090abb92e526a0c4a566cd0201aabe30d996f84d1dbb932c9e577bc5` |
| `_parse_trak` | `telegram_mcp/tools/media.py:149-163` | verbatim | `dd054a44e5db733a37b867d271962d5e2412b238088428b3f962c7a4d45b96ff` |
| `_parse_tkhd` | `telegram_mcp/tools/media.py:166-184` | verbatim | `c3c8b5db861fe748d2f12b02a963498129113d1d6069fae4fa76bb4d4ca8166a` |
| `get_effective_allowed_chat_ids` | `telegram_mcp/runtime.py:1219-1224` | modified: read environment per call, no runtime global fallback | N/A — modified |
| `send_scheduled_file` (from `send_file`) | `telegram_mcp/tools/media.py:220-329` | modified: explicit client/entity, parsed datetime, optional uploaded handle/attributes, return message, plain MP4 streaming | N/A — modified |
| `send_scheduled_text` (from `send_scheduled_message`) | `telegram_mcp/tools/messages.py:1047-1105` | modified: explicit client/entity/datetime, return message, plain text without preview | N/A — modified |

## Integration differences

- `send_scheduled_file` accepts keyword-only `uploaded` and `attributes` so the
  existing upload-before-deadline-check ordering survives. The local path remains
  available for metadata parsing. The adapter supplies real MP4 attributes or the
  previous ffprobe-duration / 1920×1080 fallback.
- Send wrappers propagate errors without sleeping or retrying. The adapter converts
  FloodWaitError to ReleaseError with seconds, retaining the persisted attempted
  part in `sending` without an ID for reconciliation.
- Empty or missing `TELEGRAM_ALLOWED_CHAT_IDS` disables the optional allowlist.
  Otherwise the resolved channel must be permitted before upload. This is a second
  boundary, not a replacement for approval or TELEGRAM_CHANNEL_ID verification.
- Upstream treats naive schedule times as UTC. The adapter passes aware ISO time
  from the release's Europe/Moscow conversion.
- No MCP decorators/runtime, account configuration, albums, topics, custom emoji,
  path discovery, transcript processing, contact tools or free-form send tool.
  Existing `check_telegram` / `reconcile_telegram` remain local and unchanged.

## Maintenance

Retrieve sources with GitHub's contents API at the pinned commit. Compare each
function via AST and refresh the table and whole-file hash when updating. Keep
modified and verbatim blocks distinct, as required by Apache-2.0 §4.

The existing dependency pin `Telethon>=1.45,<2` already satisfies T3; it was not
changed. Installed version inspected offline: 1.45.0. The upstream project review
recorded Telethon as archived (without establishing an archive date). Migration to
https://github.com/kurigram-org/kurigram would require separate session, scheduling
and compatibility verification; it is not an automatic replacement.
