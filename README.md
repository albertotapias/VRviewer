# WebXR STL / OBJ Inspector

View and inspect STL and OBJ models in VR on Meta Quest (or on the desktop). Uploaded models are saved in the same folder as `index.html`, so you can reopen them later from the library or with a link like `index.html?model=part.stl`.

## Files
| File | Purpose |
|---|---|
| `index.html` | The viewer (three.js + WebXR, loaded from the jsDelivr CDN) |
| `server.py` | Zero-dependency Python 3 server: serves the folder + upload/list/delete API |
| `api.php` | The same API for ordinary PHP hosting (Apache/Nginx) |

## Run it
```bash
python3 server.py            # desktop: http://localhost:8000
python3 server.py --https    # Quest over Wi-Fi: https://<PC-LAN-IP>:8443
```
WebXR only works on **HTTPS or localhost**. You can use either option:
- **`--https`**: creates a self-signed certificate with openssl (in `.certs/`, never served). In the Quest Browser, open `https://<PC-IP>:8443`, then choose *Advanced → Proceed* once.
- **USB + adb**: run `adb reverse tcp:8000 tcp:8000`, then open `http://localhost:8000` on the Quest.

PHP hosting: copy the three files into a folder that the web server can write to. For large models, raise `post_max_size` and `upload_max_filesize`.

## Coordinate system
Models are treated as **Z-up** (the usual CAD/STL convention). Gravity pulls along −Z, and you walk on the XY plane at Z = 0 or on top of the model's surfaces (you can step up as much as 45 cm). For Y-up OBJ files, change *Up axis in file* to Y. *File units* (default: mm) sets the real-world scale. Models with an implausible size are auto-fitted to 1 m.

## Quest controls
| Input | Action |
|---|---|
| Grip | Grab the model: it follows your hand (move + rotate) |
| Both grips | Pull apart or push together to zoom, twist to rotate |
| Grip + thumbstick | ↑↓ zoom, ←→ spin around Z |
| Trigger | Pick a point (file coordinates). A 2nd point gives the distance and ΔX/ΔY/ΔZ |
| Left stick | Walk |
| Right stick | Snap turn 30°. ↑↓ moves up/down in fly mode |
| X | Model library: point and pull the trigger to open a file from the server |
| Y | Toggle walk (gravity) / fly |
| A / B | Reset pose / wireframe |
| Thumbstick click | Clear the measurement |

A wrist panel on the left controller shows the file, triangle count, size, scale, measurements and pointer coordinates.

Desktop: drag to orbit, right-drag to pan, use the wheel to zoom, click to measure. Drop files anywhere to upload them.

## Notes
- Upload names are sanitised, only `.stl`/`.obj` are accepted, and existing files are never overwritten (the new one gets a suffix, e.g. `part_1.stl`).
- The server listens on your LAN with no authentication, including delete. Run it only on networks you trust.
- OBJ materials and textures (`.mtl`) are ignored. Binary STL vertex colours are shown.
- `three-mesh-bvh` speeds up raycasts on large meshes. If it fails to load, the viewer still works, just more slowly.
