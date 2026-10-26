---
title: "From a CT scan to a glass block, in one afternoon"
date: 2026-10-26
draft: true
tags: [ct, dicom, meshes, laser-etching, three.js]
---

I started the day asking whether I could download the raw CT from a hospital's web viewer. You can't: that viewer streams rendered JPEGs, and the real data only comes as DICOM from a records request. So I asked the other question: once I have the DICOM, how do I get it into glass?

Subsurface laser engraving fires tiny fractures inside a crystal block, one dot at a time. The dots want even spacing: too close and they merge or crack, too far apart and the piece looks faint ([Paul Bourke's notes](https://paulbourke.net/miscellaneous/crystalengraving/posterA3.pdf) are the best short read). I generate dots myself, so what I really need is a clean **mesh**.

What came out of the afternoon:

- A pipeline that reads the DICOM series, sorts the slices by position (never by file name), and turns either a density threshold or a segmentation into smooth, closed meshes, one per layer, scaled into the block.
- Segmentation from [TotalSegmentator](https://awesome.ecosyste.ms/projects/1147580) instead of writing my own. The trick that made it artistic rather than clinical: the segmentation only *selects* (these ribs, that vertebra), and a recipe decides the look: how smooth, how many triangles, whether the skin is just an outer shell.
- A browser viewer that shows the meshes inside the block, as glass, solid or a rough dot preview.

What went wrong: the first public link of the viewer just sat on "Loading sample model" on someone else's machine. The page imported its 3D engine from a CDN at startup, and when that doesn't happen the script dies silently. Now the engine is bundled into the page, and if anything fails at startup the page says so in words.

<!-- screenshots wanted: field/2026-10-26/screenshots/01-viewer-glass.png (sample chest in glass mode), 02-viewer-dots.png -->
