"""Read back native executable and early Track 5 files from the packaged GDI."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sc5.cli import DEFAULT_DISC
from sc5.disc import GDImage, SECTOR, PAYLOAD
from sc5.sector import verify_mode1


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-report',type=Path,default=ROOT/'output/native-rom/package-report.json')
    args=parser.parse_args()
    package = json.loads(args.package_report.read_text('utf-8'))
    build = json.loads((ROOT/'work/native-rom/build/build-report.json').read_text('utf-8'))
    gdi = Path(package['gdi'])
    rows = [line.split() for line in gdi.read_text('ascii').splitlines()[1:]]
    row = next(row for row in rows if row[0] == '5')
    start = int(row[1])
    track = gdi.parent/row[4]
    assert start == 58499 and package['track5_index00_data_preserved']
    candidate = ROOT/'work/native-rom/build/Track5_NATIVE_KR.bin'
    track_hash = digest(track)
    assert track_hash == digest(candidate), 'Packaged track differs from native candidate'
    files = []
    with GDImage(DEFAULT_DISC) as original, GDImage(DEFAULT_DISC,track3=gdi.parent/'track03.bin',track5=track) as localized, track.open('rb') as stream:
        originals={e.name:e for e in original.entries()}
        for entry in localized.entries():
            if entry.name not in {'1ST_READ.BIN', 'MANATEE.DRV', 'SH_1.MLT', 'COMMON_DATA.PVM'}:
                continue
            data = bytearray()
            sectors = 0
            stream.seek((entry.lba-start)*SECTOR)
            for offset in range(0, entry.size, PAYLOAD):
                sector = stream.read(SECTOR)
                assert verify_mode1(sector), f'Bad EDC/ECC: {entry.name}, sector {offset//PAYLOAD}'
                data.extend(sector[16:16+min(PAYLOAD, entry.size-offset)])
                sectors += 1
            if entry.name == '1ST_READ.BIN':
                expected = (ROOT/'work/native-rom/build/1ST_READ.BIN').read_bytes()
            elif entry.name == 'COMMON_DATA.PVM':
                expected = (ROOT/'assets/pvm-edits/COMMON_DATA.PVM').read_bytes()
            else:
                old=originals[entry.name]
                expected = original.read(old.lba, old.size)
            assert data == expected, f'File readback mismatch: {entry.name}'
            files.append({'name':entry.name, 'lba':entry.lba, 'size':entry.size,
                          'sha256':hashlib.sha256(data).hexdigest(), 'valid_edc_ecc_sectors':sectors})
    executable = next(item for item in files if item['name'] == '1ST_READ.BIN')
    assert executable['sha256'] == build['executable_sha256']
    report = {'passed':True, 'gdi':str(gdi), 'track5_start_lba':start,
              'track5_sha256':track_hash, 'track5_size':track.stat().st_size,
              'files':files, 'payload_diagnostic':build['diagnostic'],
              'chd_sha256':package['chd_sha256'], 'chd_integrity':package['verification'],
              'source_disc_modified':False, 'external_subtitle_files_required':False,
              'physical_console_tested':False}
    assert not report['payload_diagnostic']
    (ROOT/'work/native-rom/package-disc-validation.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
