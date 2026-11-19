# RGB performance and Neo-Voxy boundary checks — 19 November 2026

## Current shader-only optimization candidate

This build keeps E-Lite's water/depth paths and working generated-normal
lighting unchanged by default. It trades RGB precision and more precise
long-range occupancy checks for a longer coloured-light range:

- RGB propagation: six existing compute passes, with strides `1, 1, 2, 3, 4, 5`
  (16-block maximum path instead of the original 10). Every intervening cell is tested on
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
- Moving light sources now use the rendered entity/item transform origin
  instead of one atomic write per animated vertex cell. Each vertex writes
  the **same** eight-corner normalized sub-voxel emission footprint, so light
  can slide across the world-space lattice. It remains a shadow-pass-only
  approximation: entity models with different local part transforms may still
  disagree about their origin, and there is no object-independent source list.

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
