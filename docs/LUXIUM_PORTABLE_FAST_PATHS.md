# Luxium-inspired optimization consolidation (MessyShaders / Iris 1.21.1)

Date: 19 November 2026. Target: NeoForge + Iris + Neo-Voxy, GPU-bound play,
all important E-Lite features retained. This is a **design comparison** of
approaches observed in the user's Luxium 2.8.4 pre-alpha archive. No Luxium
code or shader assets are copied, compiled, or redistributed. Its original
license is restrictive and the provided project targets Minecraft 1.20.1 with
an explicit Iris/Oculus incompatibility. Shader-pack optimizations must use
independently written GLSL and supported Iris interfaces.

## Already portable / applied to this experimental pack

| Pattern | Current implementation | Limitation / evidence needed |
| --- | --- | --- |
| Share light work across consumers | One RGB history volume is sampled by terrain, Colorwheel, Voxy opaque and Voxy water. | Check whether additional consumers actually share the same irradiance. |
| Bounded lighting structures | 48³ camera-relative RGB field and 8-bit normalized images rather than a huge frame buffer. | Source visibility fades beyond ~24 blocks; volume is rebuilt every frame. |
| Fuse adjacent GPU work | Source decoding and one-block propagation now share a single dispatch. Five subsequent diffusion dispatches retain the previous 16-block reach. | GLSL compile and frame-time comparison required to confirm speedup. |
| Avoid negligible local-light work | Moving sources skip atomic writes smaller than 8/255, below the visible RGB gate. | Measure high-entity scenes; confirm no pop at low intensity. |
| Distance-dependent material cost | Generated automatic normals have a configurable per-fragment distance cutoff (default 56 blocks). | Preserve near quality and avoid hard change under camera motion. |

## Shader-only candidates, ranked for a controlled follow-up

1. **Bloom taps / mip pyramid reuse.** E-Lite's `mipmap_bloom` samples its
   existing mip chain but evaluates per-pixel trigonometric offsets and up to
   20 texture taps. An independently written, fixed-tap Kawase-like *optional*
   filter could reduce full-screen ALU/taps without adding a new framebuffer.
   Compare bloom size, flicker, colored emissives, and ms before making default.
2. **Distance/budget control for screen-space reflection and godrays.** Work
   within E-Lite/MakeUp's existing path and add early-outs based on distance,
   projection, and source visibility. Prefer skipping rays that contribute
   nothing over reducing resolution indiscriminately.
3. **Shadow filtering guards.** Reuse E-Lite's shadow path. Gate expensive
   soft filtering when sky visibility or relevant shadow contribution is zero,
   but do not replace Iris' shadow maps with Luxium's independent renderer.
4. **Adaptive feature quality via existing config levels.** Use a bounded
   sample budget for bloom, volumetrics and reflections, with a consistent
   fast preset. No new fullscreen passes. Only apply a quality adjustment
   after the same-camera A/B comparison and explicit user acceptance.

## Requires a separate 1.21.1 client helper, not possible safely by shaders alone

| Luxium concept (architectural only) | What a compatible helper would supply | Why shader-only cannot reproduce it reliably |
| --- | --- | --- |
| Cached, section-local static lights | Immutable source positions, change notifications, dirty-section updates, bounded GPU uploads | Iris shadow pass only sees rendered geometry; shader `entityId`/`blockId` is a category, not a complete loaded-world source list. |
| Spatially tiled dynamic-light lists | Actual per-entity/item XYZ, RGB/radius, stable identity, screen tile bins | The per-draw shader has no guaranteed entity origin; a matrix-only guess caused camera-attached light in build #93. |
| Limited, incremental shadow atlas updates | Shadow caster changes, light visibility sets and renderer-owned cache lifecycle | Iris owns its shadow pipeline. Luxium's source and hooks cannot be transplanted into Iris without renderer conflicts. |
| Mesh/occlusion culling and static material batching | World renderer/Embeddium integration with ownership of draw lists | A shader pack cannot decide which world meshes Minecraft submits or how Voxy builds distant geometry. |

The recommended helper would be **separate from the shader**, not invasive
mixins into C2ME/OpenCL or Voxy. It should expose minimal public data, batch
updates and add at most one bounded GPU upload per frame. Do **not** implement
one without a stable Iris-facing interface and profiling: extra CPU state and
uploads can cost more than the current compact shader-only approximation.

## Baseline and acceptance criteria

- Compare unmodified E-Lite 5.1.3, last good shader build #92, and corrected
  fused-pass build in the same scene/settings. Record median GPU frame ms and
  1% lows, not just average FPS; include 1/50/500 lights and a busy crowd.
- Verify still-working auto materials, LabPBR fallback, water, Voxy shading,
  blocklight tint, emitted bloom, entity shadows and shadow occlusion.
- Specifically test an emitter moving independently of the player; light
  must remain on the emitter and avoid jumping between block centers.
- Test a placed sea lantern behind/across a wall at 4, 12, 20, and 28 blocks
  camera distance. The 48³ camera-relative source limit is not fixed by
  longer diffusion strides or postprocess filters.
- Report shader compile success separately from in-game visual correctness
  and measured GPU improvement; neither is implied by static tests.

Sources: supplied E-Lite 5.1.3 shader ZIP, Luxium 2.8.4-pre-alpha archive
`NOTICE.md` and `README.md`, and MessyShaders' own `FAST_PATH_AUDIT.md`.
