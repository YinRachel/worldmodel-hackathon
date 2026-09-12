# Empty Room → Your Next Room

An AI room redesign prototype that turns a room photo into a furnished preview and a short video.

## About

Choosing furniture online makes it difficult to imagine how it will look in your own space. This prototype connects furniture shopping with AI room visualization.

Upload a room photo, mark unwanted furniture for removal, search real shopping listings, and select a sofa. Describe where it should go, generate a furnished preview, and turn that preview into a short AI video.

The project connects your existing room to a visualization using a real product reference, without requiring manual image editing or 3D modelling.

## Features

1. **Upload a room photo** to start redesigning your space.
2. **Remove unwanted furniture** by manually selecting the area to edit.
3. **Find furniture** through UK Google Shopping results.
4. **Generate a furnished preview** using the selected product image and a placement instruction.
5. **Create a short room video** from the furnished preview.

## Technology and Models

The application uses a Python backend and an HTML/JavaScript browser interface.

| Task | Provider | Model / service identifier |
|---|---|---|
| Selected-object removal and room clearing | Runware | `runware:102@1` |
| Sofa insertion using room and product reference images | Google model accessed through Runware | `google:4@3` |
| Video generation from the furnished preview | Reactor | `reactor/helios` |
| Furniture search | SerpApi | Google Shopping engine: `google_shopping` |

These are the exact identifiers configured in the code. The project integrates existing models; it does not train its own model.

## Required APIs

You need API keys for all three services to use the complete workflow:

| Service | Used for | Environment variable | Alternative local key file |
|---|---|---|---|
| Runware | Furniture removal and insertion | `RUNWARE_API_KEY` | `runware_api_key.txt` |
| SerpApi | Furniture shopping search | `SERPAPI_API_KEY` | `serpapi_key.txt` |
| Reactor | Helios video generation | `REACTOR_API_KEY` | `api_key.txt` |

Your accounts need sufficient credits and access to the configured models.

### Option 1: Environment variables

Set these in the terminal where you will run the application:

```bash
export RUNWARE_API_KEY="your_runware_api_key"
export SERPAPI_API_KEY="your_serpapi_api_key"
export REACTOR_API_KEY="your_reactor_api_key"
```

The application reads these variables directly. It does not automatically load a `.env` file.

### Option 2: Local key files

Create these files in the project root, alongside `select_room.py`:

```text
runware_api_key.txt
serpapi_key.txt
api_key.txt
```

Each file should contain only its corresponding API key, without quotes or variable names.

Environment variables take priority over local key files. These key filenames are included in `.gitignore`; do not commit API keys to GitHub.

## Run Locally

Use Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
mkdir -p outputs
python select_room.py
```

Open **http://127.0.0.1:8000** in your browser.

## How to Use

1. Upload a room photograph.
2. Mark the furniture you want to remove and generate a cleaning result.
3. Review the result, repeat cleaning if needed, and click **Use this room**.
4. Search for a sofa and select a product with an image.
5. Describe where the sofa should go and click **Insert selected furniture**.
6. Review the furnished preview.
7. Enter a camera movement prompt, choose a duration, and generate a Helios video.
8. Download your generated images and video.

## Current Limitations

- This is an early prototype, with insertion currently tailored to sofas.
- Object removal uses manual selection rather than automatic object detection.
- Some removal prompts are tailored to the supplied demo room.
- Furniture scale and placement are visual estimates; physical fit is not verified.
- Generated furniture details and room appearance may vary.
- Shopping results use product thumbnails; confirm prices, availability, and dimensions with the retailer.
- Video output is an AI-generated preview, not a measured 3D reconstruction.
- Generation requires external API access and is subject to credits, latency, and service capacity.

## Future Work

- Dimension-aware furniture placement.
- Better preservation of product appearance and room details.
- Support for more furniture categories.
- More general room-clearing prompts.
- Easier comparison of alternative designs.
