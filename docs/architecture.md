# ulanzi-linux — Architecture

Clean-architecture layering, adapted to a small Python library / CLI.

```text
┌───────────────────────────────────────────────────────────────────────┐
│  Interface layer  —  src/ulanzi_linux/interface                       │
│    CLI (Click + Rich), FastAPI web editor, desktop wrapper            │
└───────────────────────────────────────────────────────────────────────┘
                  │ calls
                  ▼
┌───────────────────────────────────────────────────────────────────────┐
│  Application layer — src/ulanzi_linux/application                     │
│    DeckService, DeckDaemon, config loader/watcher, action runner      │
└───────────────────────────────────────────────────────────────────────┘
                  │ uses abstractions
                  ▼
┌───────────────────────────────────────────────────────────────────────┐
│  Domain layer — src/ulanzi_linux/domain                               │
│    DeckDevice (abstract), DeckSpec, ButtonEvent, DeviceInfoEvent,     │
│    IntEnums for protocol codes. NO external deps.                     │
└───────────────────────────────────────────────────────────────────────┘
                  ▲ implements
                  │
┌───────────────────────────────────────────────────────────────────────┐
│  Infrastructure layer — src/ulanzi_linux/infrastructure               │
│    HidApiTransport, UlanziD200Device, packet framing (construct)      │
└───────────────────────────────────────────────────────────────────────┘
```

## Rules of the layer cake

1. `domain` depends on nothing.
2. `application` depends only on `domain`.
3. `infrastructure` implements `domain` interfaces; the application sees
   only the abstract contracts.
4. `interface` orchestrates `application` — it never touches
   `infrastructure` directly.
5. `observability` is a cross-cutting concern and may be imported from
   any layer, but holds no business state.

## Why this structure

- **Testability** — `DeckService` is tested with a `FakeDeck` that never
  touches USB. Protocol serialization is tested with plain bytes, no
  device required.
- **Swapability** — adding the D300, D400, or any future Ulanzi deck is a
  new `DeckDevice` implementation; nothing above the infrastructure layer
  changes.
- **Observability-first** — every command emits structured logs with the
  fields future-you will want in Grafana or Tempo.
- **Shared editor contract** — the browser UI and the installable desktop
  window both use the same FastAPI app and static frontend, so feature work
  for the editor lands once and stays consistent across both entry points.

## Runtime model

- Reads are performed by a dedicated asyncio task owned by
  `UlanziD200Device`. Parsed events are pushed into a bounded
  `asyncio.Queue`; when full we drop the oldest to favour liveness over
  history.
- Writes are serialised inside `HidApiTransport` with an `asyncio.Lock`
  so CLI foreground calls and background services can share the same
  device safely.
- Blocking `hid.device` calls run inside
  `loop.run_in_executor(None, ...)` so the asyncio event loop never
  stalls on USB I/O.

## Future directions

- OpenTelemetry exporter wired into `observability/` for traces and
  metrics.
- HTTP daemon (FastAPI) so other hosts on the LAN can drive the deck.
- Richer desktop packaging (AppImage / Debian package) on top of the current
  pywebview-based launcher.
