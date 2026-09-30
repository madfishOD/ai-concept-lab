# Local reference library

Only `index.json` (IDs, tags, relative filenames and provenance descriptions) is versioned.
All reference images remain local in `library/images/`; Git and Git LFS must not contain them.

After cloning, copy your authorized reference PNGs into this directory using the filenames
listed in `index.json` (initial set: `NOC002_ING.png` through `NOC006_ING.png`).
The prototype needs these local images to display references and run its visual planner.
No images are downloaded automatically from the game repository or a cloud service.

The initial metadata describes candidates, not art-lead-approved standards. Keep that
distinction when extending the library. On this PC the existing images are retained.
