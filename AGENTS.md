# MessyShaders instructions for Codex

Target Minecraft **1.21.1**, Iris, Neo-Voxy, E-Lite 5.1.3, and a GPU-bound modpack.

The **stable, tester-accepted shader baseline** is branch
`feature/elite-pbr-voxy-fog` (v15 of `MessyShaders-E-Lite-PBR-Voxy.zip`).
It includes functioning automatic PBR materials, Colorwheel and machine
shadows, Voxy support, cloud occlusion, and blended near/far water. The tiny
remaining Voxy water/geometry seam also occurs with Complementary; the user
has marked the **shader water work complete**. Do not reopen or rewrite water
as part of unrelated performance work.

For any **Luxium-style performance** request, read
[`docs/CODEX_LUXIUM_OPTIMIZATION_HANDOFF.md`](docs/CODEX_LUXIUM_OPTIMIZATION_HANDOFF.md)
before changing source. It separates actual test failures, ideas requiring a
client helper, measurable shader-only candidates and acceptance gates.

Important constraints:

- Treat Luxium as a **conceptual architecture reference only**. Never copy,
  compile or redistribute its restrictive, decompiled source.
- Start new optimizations from the working E-Lite branch, not experimental RGB
  branches. Test **one isolated, toggleable fast path at a time**.
- No C2ME/OpenCL changes and no Voxy, Iris or Minecraft mixins for shader-side
  optimization. A separate minimal helper is only a *proposal* until agreed.
- Preserve PBR, Colorwheel shadows, Voxy, water appearance, clouds and vanilla
  E-Lite parity. No reduced-feature benchmark disguised as a speedup.
- Report actual GPU/frame-time measurements and visual regression results;
  packaging/unit-test success is not in-game proof.

For the clean shader builder, run:

```bash
python3 tools/build_elite_materials_voxy.py
python3 -m unittest discover -s tests -q
```

Do not modify pre-existing user changes in another branch or worktree.
