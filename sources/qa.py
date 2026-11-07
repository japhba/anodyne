#!/usr/bin/env python3
"""Run documented FontBakery checks on alternative installation cohorts."""
from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
POLICY = Path(__file__).with_name('qa-policy.json')
BLOCKING = {'FAIL', 'ERROR', 'FATAL'}


def gpos7_lookups(font):
    """Equivalent read-only test, without copying unrelated outline tables."""
    if 'GPOS' not in font or not font['GPOS'].table.LookupList:
        return []
    found = []
    for index, lookup in enumerate(font['GPOS'].table.LookupList.Lookup):
        if lookup.LookupType == 7:
            found.append(index)
        elif lookup.LookupType == 9:
            for subtable in lookup.SubTable:
                if subtable.ExtensionLookupType == 7:
                    found.append(index)
                    break
    return found


def check_id(check):
    for value in check.get('key', []):
        if isinstance(value, str) and value.startswith('<FontBakeryCheck:'):
            return value.removeprefix('<FontBakeryCheck:').removesuffix('>')
    return check.get('check_id', '')


def diagnostic_message(log):
    message = log.get('message', '')
    return message.get('message', '') if isinstance(message, dict) else str(message)


def exception_for(check, log, rules):
    message = log.get('message', {})
    code = message.get('code') if isinstance(message, dict) else None
    points = {cp.upper() for cp in re.findall(r'U\+([0-9A-Fa-f]{4,6})', diagnostic_message(log))}
    for rule in rules:
        if (check_id(check) == rule['check'] and code == rule['code']
                and fnmatch.fnmatch(check.get('filename', ''), rule['filename'])
                and points == set(rule.get('only_codepoints', []))):
            return rule
    return None


def summarize(report, rules):
    result = {'raw_counts': report.get('result', {}), 'blocking': [],
              'accepted_diagnostics': [], 'warnings': []}
    for section in report.get('sections', []):
        for check in section.get('checks', []):
            for log in check.get('logs', []):
                status = log.get('status')
                if status not in BLOCKING | {'WARN'}:
                    continue
                row = {'check': check_id(check), 'font': check.get('filename'),
                       'status': status, 'message': diagnostic_message(log)}
                exception = exception_for(check, log, rules) if status in BLOCKING else None
                if exception:
                    row['kind'] = exception.get('kind', 'documented_exception')
                    row['reason'] = exception['reason']
                    row['evidence'] = exception['evidence']
                    result['accepted_diagnostics'].append(row)
                else:
                    result['blocking' if status in BLOCKING else 'warnings'].append(row)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fonts', type=Path, default=ROOT / 'fonts')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/fontbakery')
    parser.add_argument('--full', action='store_true', help='run every universal outline/interpolation diagnostic too')
    parser.add_argument('--cohort', choices=['static', 'variable'])
    args = parser.parse_args()
    policy = json.loads(POLICY.read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    summary = {'mode': 'full universal' if args.full else 'selected release checks',
               'policy': str(POLICY), 'policy_contents': policy, 'cohorts': {}}
    for cohort in ([args.cohort] if args.cohort else ['static', 'variable']):
        fonts = sorted((args.fonts / cohort).glob('*.ttf'))
        if not fonts:
            parser.error(f'no fonts in {args.fonts / cohort}')
        report_path = args.out / f'{cohort}.json'
        command = [sys.executable, '-m', 'fontbakery', 'check-universal', '--skip-network',
                   '-J', '1', '--json', str(report_path)]
        if not args.full:
            for check in policy['release_checks']:
                command += ['-c', check]
        command += list(map(str, fonts))
        print(f'FontBakery {cohort}: {summary["mode"]}', flush=True)
        with (args.out / f'{cohort}.log').open('w') as log:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        if not report_path.exists():
            raise RuntimeError(f'FontBakery failed without a report; see {args.out / (cohort + ".log")}')
        result = summarize(json.loads(report_path.read_text()), policy['exceptions'])
        result['read_only_checks'] = []
        if not args.full and 'gpos7' in policy.get('read_only_checks', []):
            from fontTools.ttLib import TTFont
            for path in fonts:
                with TTFont(path) as font:
                    lookups = gpos7_lookups(font)
                row = {'check': 'gpos7', 'font': path.name, 'status': 'WARN' if lookups else 'PASS',
                       'lookup_indices': lookups,
                       'message': 'GPOS7 lookups may be ignored by older CoreText shapers' if lookups else 'Font has no GPOS7 lookups'}
                result['read_only_checks'].append(row)
                if lookups:
                    result['warnings'].append(row)
        result['exit_code'] = process.returncode
        if process.returncode not in (0, 1):
            result['blocking'].append({'check': 'runner', 'status': 'ERROR',
                                       'message': f'FontBakery exited {process.returncode}'})
        summary['cohorts'][cohort] = result
        print(f'  {len(result["blocking"])} blocking diagnostics, '
              f'{len(result["accepted_diagnostics"])} scoped exceptions, {len(result["warnings"])} warnings', flush=True)
    destination = args.out / 'summary.json'
    destination.write_text(json.dumps(summary, indent=2) + '\n')
    for result in summary['cohorts'].values():
        for row in result['blocking']:
            print(f'FAIL {row["check"]} {row.get("font", "")}: {row["message"]}', flush=True)
    print('Report:', destination)
    raise SystemExit(any(result['blocking'] for result in summary['cohorts'].values()))


if __name__ == '__main__':
    main()
