Offline cache files for fixed Guangzhou Panyu map mode.

Expected files:
- scenario_small.json
- scenario_medium.json
- scenario_large.json
- routes_small.json
- routes_medium.json
- routes_large.json

Behavior:
- The first successful online map run for Guangzhou Panyu will save the scenario JSON automatically.
- Successful route geometry fetches are appended into the matching routes_<scale>.json file.
- Later runs can reuse these files locally without requesting AMap again.
