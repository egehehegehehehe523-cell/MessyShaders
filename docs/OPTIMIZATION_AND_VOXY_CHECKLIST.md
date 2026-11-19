# RGB performance and Neo-Voxy boundary checks — 19 November 2026

## Current shader-only optimization candidate

This build keeps E-Lite's water/depth paths and working generated-normal
lighting unchanged by default. It trades RGB precision and more precise
long-range occupancy checks for a longer coloured-light range:

- RGB propagation: **six mathematical propagation steps in five standalone
  passes**, with strides `1, 1, 2, 3, 4, 5`. Step one is fused with the
  initial palette/seed decode, eliminating a whole 48³ intermediate pass and
  a dispatch while preserving the same light spread. The output remains A,
  so the temporal renderer and Voxy samplers need no changes.
  The maximum path is 16 blocks instead of the original 10. Every intervening cell is tested on
  a multi-block jump. Empty light candidates skip those occupancy lookups.
- Four 48³ RGB volumes: `RGBA8` in place of `RGBA16F`. Source intensities are
  bounded to `[0, 1]`. This changes the light-field allocation from 3,538,944
  to 1,769,472 bytes; it does **not** guarantee a proportional FPS gain.
  The two R32UI voxel grids are unchanged.
- The common RGB sampler uses stronger per-block illumination and a gentle
  low-energy tail, and fades the last
  few voxels of the 48³ camera-centred field. This applies to near terrain,
  Colourwheel, Voxy opaque and Voxy water. It does not extend the field beyond
  its ~24-block radius.
- Shader settings > Messy Features > **Automatic Normal Distance** defaults
  to 56 blocks, preserving the last working normal appearance. A value of
  24/32/40 reduces the terrain area paying for four extra albedo samples per
  pixel. This is a *quality/performance* choice, not an automatic benchmark.
- Moving lights sample the **actual shadow-transformed entity/item vertices**
  and distribute each source across eight neighboring voxels. This fixes the
  previous matrix-origin regression, which could place light at the player.
  Each vertex has its own continuous world position: larger or heavily animated
  entities still produce an approximate surface-shaped glow, not a single
  stable entity-wide source. That requires positions supplied by a helper or
  another supported entity-position API; shader entity IDs alone are not enough.
- Moving emitter sub-voxel corner writes below `8/255` energy are suppressed
  before the atomic operation. Those contributions cannot pass the existing
  shared RGB energy cutoff, so they consume GPU writes without visible light.

### What stock E-Lite actually limits

- E-Lite 5.1.3 does **not** contain a true coloured voxel-light propagation
  volume; this is a MessyShaders addition. Its regular placed light is vanilla
  block light (levels 0–15, up to ~15 blocks), optionally tinted in the shader.
- E-Lite's **Fake dynamic light** for recognised held items uses
  `max(1 - gl_FogFragCoord * 0.0666 - itemOffset, 0)`, reaching zero at about
  15 blocks at best, or sooner for dimmer item classes. It is a camera-based
  approximation, not RGB world-space lighting from arbitrary moving entities.
- Our RGB contribution currently travels up to 16 blocks from a source **but**
  is computed only inside a camera-centred 48³ field (roughly ±24 blocks per
  axis, with a further 4-voxel edge fade). Distant lamps outside that field
  cannot illuminate a nearby wall with our RGB path, and a source near its edge
  has its outward spill clipped. A wider field would raise compute cost;
  increasing propagation strides alone cannot solve this.

**Unverified:** FPS, GPU milliseconds, camera-motion banding from RGBA8,
moving-source origin consistency across custom renderers, wall occlusion on
unusual block shapes, visual coloured-light range, and the voxel boundary fade.
Compare against the previous working build (#91) and #92 before changing other
effects. Disable this candidate if it causes new banding.

## Telling a shader seam from a Neo-Voxy seam

1. Use the same position, render distance, loaded/generated region, weather
   and time of day with Neo-Voxy enabled **without any shader pack**. Note
   whether the hole/terrain cutoff already appears there.
2. Use MessyShaders with precisely the same Neo-Voxy configuration. A gap,
   missing ring, or identical cutoff in vanilla is evidence for a Neo-Voxy
   geometry/loading/culling issue. Only a brightness/colour mismatch that
   appears with MessyShaders is a plausible pack-side shading defect.
3. For this pack, **leave Neo-Voxy's Circular LOD Fade enabled** during the
   test: MessyShaders has not implemented its own geometry crossfade. When
   comparing with a *different* shader that supplies its own LOD fade, disable
   Neo-Voxy's fade to avoid two competing transitions.
4. Confirm the area was actually loaded or imported into the Voxy LOD cache.
   LOD draw distance does not manufacture unseen terrain data. If a mod update
   made an old cache inconsistent, back up its world/cache first and follow
   Neo-Voxy's documented reset procedure; do not erase worlds or caches as a
   generic shader troubleshooting step.
5. For a follow-up bug report, record the Neo-Voxy fork/version, Iris version,
   vanilla and LOD distances, Circular LOD Fade state, and comparable frames
   with vanilla, the #91 shader build, and this build.

Neo-Voxy maintainers explicitly warn about double fading:
<https://github.com/Lappuda/neo-voxy>. Their documented circular handoff is
implemented in the renderer, not in shader-pack fragment shading.

No Neo-Voxy code, mixins, cache sizing, chunk queues, or RAM defaults are
modified by this shader build. An upstream geometry-gap fix would require a
separate, evidence-based mod change.

## Next measured optimization phase

The Luxium reference is a separately implemented renderer with CPU-side
state and caching. A shader ZIP has no equivalent general-purpose dirty-chunk
event stream. Further large savings would need measurements of RGB volume
clears, the six propagation passes, shadow voxel writes, normal sampling,
reflections and volumetrics. On each candidate, compare median/p95/p99 GPU
frame time and visual output in identical torch/cave, daylight texture, dense
entity, rain/water and LOD scenes. Do not claim a Luxium-level speedup until
those timings exist.
