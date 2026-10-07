"""Stage the verified v0.85 graphics repair for the existing public release."""
import csv,json,shutil,subprocess,sys
from pathlib import Path
from prepare_public_v08 import ROOT,PUBLIC,ORIGINAL,sha,copy,write_json

RELEASE=ROOT/'work/github-v0.85'
PATCH=RELEASE/'DC-Space-Channel-5-Kr-v0.85-Patch'
OLD=ROOT/'work/github-v0.81/DC-Space-Channel-5-Kr-v0.81-Patch'
REVIEW=ROOT/'work/save-boss-review-20261007'
TARGET=ROOT/'output/native-rom-fixed'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    proof=json.loads((REVIEW/'repair-checkpoint.json').read_text('utf-8'))
    validation=json.loads((ROOT/'work/native-rom/package-disc-validation.json').read_text('utf-8'))
    assert validation['passed'] and validation['chd_sha256']==proof['package']['chd_sha256']
    assert proof['boss_vram_proof']['all_loaded_boss_textures_byte_exact']
    RELEASE.mkdir(exist_ok=False)
    (PATCH/'patches').mkdir(parents=True)
    shutil.copytree(OLD/'bin',PATCH/'bin')
    for path in (ROOT/'sc5').glob('*.py'):copy(path.relative_to(ROOT))
    for name in ('hud.c','judgment.c','judgment_vmu.c','subtitles.c','link.ld','sector_retime.c','sector_retime.dll'):
        copy(Path('native')/name)
    for name in ('build_native_editor.py','build_native_subtitles.py','native_entry.py','verify_native_rom.py',
                 'release_patcher.py','prepare_public_v085.py','fix_warning_glyphs.py'):
        copy(Path('tools')/name)
    for name in ('edits.json','font_policy.json'):
        write_json(PUBLIC/'data'/name,json.loads((ROOT/'data'/name).read_text('utf-8')))
    for name in ('image_text_review.jsonl','stage_caption_review.jsonl'):
        copy(Path('data')/name)
    shutil.copy2(ROOT/'data/text_export.csv',PUBLIC/'data/localization_export.csv')
    for name in ('COMMON_DATA.PVM_114.png','COMMON_DATA.PVM_115.png','COMMON_DATA.PVM_291.png','SET_JUDGMENT_2.png'):
        copy(Path('assets/image-edits')/name)
    launcher='@echo off\r\ncd /d "%~dp0"\r\nstart "" "%~dp0SC5KoreanWorkbench_v12.exe" --project "%~dp0."\r\n'
    (PUBLIC/'run_workbench.cmd').write_bytes(launcher.encode('ascii'))
    progress=json.loads((PUBLIC/'data/localization_progress.json').read_text('utf-8'))
    progress.update(native_editor='SC5KoreanWorkbench_v12.exe',
                    native_editor_status='v12 includes native-size warning glyphs and compact lossless HUD packing',
                    latest_batch='v0.85 save warning, SAVE UV and Report 1 boss VRAM repairs')
    write_json(PUBLIC/'data/localization_progress.json',progress)
    for name,relative in {
        'native-disc.json':'work/native-rom/package-disc-validation.json',
        'graphics-repair.json':'work/save-boss-review-20261007/repair-checkpoint.json',
        'boss-vram.json':'work/save-boss-review-20261007/combined/boss-playing-clean-vram.json',
        'compact-hud.json':'work/native-rom/build/hud-overlay-proof.json',
        'warning-rendering.json':'work/save-boss-review-20261007/warning-smoothing-verification.json',
        'candidate-final-code.json':'work/save-boss-review-20261007/combined-candidate/final-executable-comparison.json',
        'candidate-final-common.json':'work/save-boss-review-20261007/combined-candidate/final-common-comparison.json',
        'editor-v12-bundle.json':'work/native-editor-build.json',
    }.items():write_json(PUBLIC/'docs/verification'/name,json.loads((ROOT/relative).read_text('utf-8')))
    screenshots={
        '16-save-screen-v085.png':('combined/screenshots/combined-save-check.png','native_candidate_capture'),
        '17-save-warning-v085.png':('save-warning-fixed-in-game.png','native_candidate_crop_2x_nearest'),
        '18-boss-gameplay-v085.png':('combined/screenshots/boss-play-011.png','native_candidate_capture'),
        '19-gameplay-hud-v085.png':('combined/screenshots/combined-hud-check.png','native_candidate_capture'),
    }
    evidence=json.loads((PUBLIC/'docs/verification/screenshots.json').read_text('utf-8'))
    for row in evidence['screenshots']:
        if row['kind']=='current_native_rom_capture':row['kind']='previous_native_rom_capture'
    for name,(source,kind) in screenshots.items():
        path=REVIEW/source;shutil.copy2(path,PUBLIC/'docs/screenshots'/name)
        evidence['screenshots'].append({'file':name,'sha256':sha(path),'kind':kind,'captured_version':'v0.85 repair candidate',
            'source':'work/save-boss-review-20261007/'+source,'stock_core_unmodified':True,'savestate_loaded':False,
            'final_build_difference':'AFS identifier relocation and previously approved COMMON 115 VQ packing; HUD hook, warning, overlay identical'})
    evidence.update(version='v0.85',chd_sha256=proof['package']['chd_sha256'])
    write_json(PUBLIC/'docs/verification/screenshots.json',evidence)
    manifest=json.loads((OLD/'manifest.json').read_text('utf-8'))
    manifest.update(version='v0.85',editor='SC5KoreanWorkbench_v12.exe')
    for track in manifest['tracks']:
        original=ORIGINAL/track['source_name'];target=TARGET/track['output_name']
        assert sha(original)==track['source_sha256']
        track.update(output_size=target.stat().st_size,output_sha256=sha(target))
        if track.get('patch'):
            subprocess.run([str(PATCH/'bin/xdelta3.exe'),'-9','-e','-s',str(original),str(target),str(PATCH/track['patch'])],check=True)
            track['patch_sha256']=sha(PATCH/track['patch'])
            print(json.dumps({'encoded':track['patch'],'size':(PATCH/track['patch']).stat().st_size}),flush=True)
    chd=Path(proof['package']['chd'])
    assert sha(chd)==proof['package']['chd_sha256']
    manifest.update(chd_size=chd.stat().st_size,chd_sha256=sha(chd),
                    gdi_text=(TARGET/'Space Channel 5 Korean Native.gdi').read_text('ascii'),
                    graphics_repair={'native_warning_font_pixels':16,'HUD_VRAM_saved_bytes':391168,
                        'boss_original_texture_bytes_preserved':True,'physical_console_tested':False})
    for tool in manifest['tools']:assert sha(PATCH/tool['file'])==tool['sha256']
    write_json(PATCH/'manifest.json',manifest)
    write_json(PUBLIC/'docs/original-and-output-hashes.json',manifest)
    shutil.copy2(ROOT/'tools/release_patcher.py',PATCH/'release_patcher.py')
    print(json.dumps({'staged':str(PATCH),'chd_sha256':manifest['chd_sha256']}),flush=True)


if __name__=='__main__':main()
