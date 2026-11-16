# Film Sound

From Claude Blender Skills by Mr omi (MIT). Sound for a rendered shot, built from its 3D motion. The shots are in `blender-film`; the scripts are in `pipelines/film/` and `pipelines/car-film/`.

## Sound from motion
`pipelines/film/scripts/11_motion_data.py` runs in Blender and reads, for every frame the edit uses: the active camera, the hero's distance, radial speed (+ = moving away), pan (−1 to 1), camera and hero speed, throttle (thrust / 9.81), camera and hero height, and the nearest moving cars within 60 m. It writes `audio/motion.json` (24 fps). `pipelines/film/scripts/12_build_sfx.py` (plain Python: numpy, scipy, ffmpeg) turns that into a 48 kHz stereo mix:

| Value | Drives |
|---|---|
| throttle | motor RPM → pitch, brightness, level; prop-wash bursts on throttle punches |
| radial speed | Doppler, `343 / (343 + radial)`: pitch drops as it passes the lens |
| pan | equal-power pan |
| distance | gain 1.2 m / distance, air absorption (less high end when far) |
| hero height | spray hiss below 2.4 m over the wet road, close shots only |
| camera speed | wind rumble and whistle (the chase camera reaches 28 m/s) |
| camera height | wet-road traffic grows as the camera gets low; a darker, distant city up high |
| shot | rooftop air-con only on the roof shot; reverb amount per shot |
| cars | a pass-by at each car's closest approach, gain and pan from the scene; wet-tyre hiss |

Street-canyon reverb: early reflections off the facades and a 1.4 s tail. Sources go in `audio/src/`; the output is `audio/sfx_mix_raw.wav` plus one file per layer in `audio/stems/`.

## Recordings first
Real CC0 recordings (BigSoundBank) sounded better than generated ones: drone, city at night, wet-road traffic, horns, a distant siren, wind, rain on a puddle, an air-conditioner. Synthesis is only a thin layer on top (the racing-quad buzz).

## Two mixes, pick by ear
Make two versions, a calm night and full city chaos, and listen. Calm won: let the hero be the star. In `12_build_sfx.py` the chaos is its own stem (`chaos`, −9 dB in `LEVEL`). Deliver at −14 LUFS (`ffmpeg -i mix.wav -af loudnorm=I=-14 out.wav`), and check that the final sound is the approved mix before you encode.

## The ffmpeg mix with ducking
`pipelines/car-film/tools/mix.sh` builds the 20 s `audio/mix.wav` from the files in `audio/norm/`. Each sound gets a start (`adelay`), volume, trim (`atrim`) and fades (`afade`). Effects and music share one bus that drops while a voice speaks; then the voice lines join:
```
[a0]...[m2]amix=inputs=13:normalize=0,volume=0.3:enable='between(t,8.35,10.35)+between(t,17.75,19.95)'[bus];
[bus][v1][v2]amix=inputs=3:normalize=0,atrim=0:20,afade=t=out:st=19:d=1,alimiter=limit=0.9[out]
```
`normalize=0` keeps every volume as written. The voice lines start at 8.5 s and 17.9 s, so each duck opens 0.15 s early. The storyboard asked for −6 dB; the script uses `volume=0.3`. `pipelines/car-film/tools/render_all.sh` muxes `audio/mix.wav` into each shot and the film (AAC). `pipelines/film/tools/clay_assemble.sh` writes picture only: add the mix afterwards.

## ElevenLabs (paid)
Generated effects, music and voice cost money: confirm with the user before any call. The key comes only from the `ELEVENLABS_API_KEY` environment variable; never ask for it in chat or write it to a file.
- `pipelines/car-film/scripts/gen_sfx.py`: ten effects (a prompt and a duration each) and a 14 s piano track. Writes `<name>.mp3` in the current folder and skips files that exist.
- `pipelines/forest/scripts/gen_sfx.py`: effects only, standard library, writes `~/blender-forest/audio/`, stops if the key is missing.
The car film's two voice lines also came from ElevenLabs; neither script makes voice.

## Cut with music in Blender
`scripts/vse_edit.py` (`blender-video-editing`) is the scripted cut: clips or frame folders, crossfades, a title, music with fades, H.264/AAC out.
```
scripts/vse_edit.py -- --clips //renders/sh010/ //renders/sh020/ --crossfade 12 --audio //audio/mix.wav --audio-fade 1.0 --out //edit.mp4 --render
```
