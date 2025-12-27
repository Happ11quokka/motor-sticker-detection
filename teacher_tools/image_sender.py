import argparse
import json
import time
from pathlib import Path
from typing import List, Dict
import sys

import requests
from tqdm import tqdm

import config


def load_students(student_file: Path) -> List[Dict]:
    with open(student_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return [s for s in data['students'] if s.get('active', True)]


def load_images(image_folder: Path) -> List[Path]:
    image_extensions = ['.jpg', '.jpeg', '.png']
    images = []
    for ext in image_extensions:
        images.extend(list(image_folder.glob(f"*{ext}")))
        images.extend(list(image_folder.glob(f"*{ext.upper()}")))
    return sorted(images)


def send_image(api_url: str, image_path: Path, timeout: int = config.DEFAULT_TIMEOUT) -> Dict:
    """이미지를 학생 API에 업로드 (분석은 서버에서 비동기로 처리)"""
    try:
        with open(image_path, 'rb') as f:
            files = {'file': (image_path.name, f, 'image/jpeg')}
            response = requests.post(
                f"{api_url}/upload",
                files=files,
                timeout=timeout
            )

        if response.status_code == 200:
            return {
                'success': True,
                'status_code': response.status_code,
                'data': response.json()
            }
        else:
            return {
                'success': False,
                'status_code': response.status_code,
                'error': response.text
            }

    except requests.exceptions.Timeout:
        return {
            'success': False,
            'error': f'Timeout after {timeout} seconds'
        }
    except requests.exceptions.ConnectionError:
        return {
            'success': False,
            'error': 'Connection failed - server may be down'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def send_images_to_student(
    student: Dict,
    images: List[Path],
    interval: float,
    timeout: int
) -> Dict:
    print(f"\n학생: {student['name']} ({student['student_id']})")
    print(f"API URL: {student['api_url']}")
    print(f"전송할 이미지: {len(images)}개\n")

    results = {
        'student': student,
        'total': len(images),
        'success': 0,
        'failed': 0,
        'details': []
    }

    for image_path in tqdm(images, desc=f"{student['name']} 전송 중"):
        result = send_image(student['api_url'], image_path, timeout)

        if result['success']:
            results['success'] += 1
            status = "✓"
        else:
            results['failed'] += 1
            status = "✗"

        results['details'].append({
            'image': image_path.name,
            'status': status,
            'result': result
        })

        if interval > 0 and image_path != images[-1]:
            time.sleep(interval)

    print(f"\n결과: 성공 {results['success']} / 실패 {results['failed']}\n")

    return results


def send_images_parallel(
    students: List[Dict],
    images: List[Path],
    interval: float,
    timeout: int
) -> List[Dict]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    print(f"병렬 모드: {len(students)}명의 학생에게 동시 전송\n")

    all_results = []

    with ThreadPoolExecutor(max_workers=len(students)) as executor:
        futures = {
            executor.submit(send_images_to_student, student, images, interval, timeout): student
            for student in students
        }

        for future in as_completed(futures):
            student = futures[future]
            try:
                result = future.result()
                all_results.append(result)
            except Exception as e:
                print(f"\n학생 {student['name']} 처리 중 오류: {e}\n")
                all_results.append({
                    'student': student,
                    'error': str(e)
                })

    return all_results


def print_summary(all_results: List[Dict]):
    print("\n" + "="*70)
    print("전송 결과 요약")
    print("="*70)

    for result in all_results:
        student = result['student']
        if 'error' in result:
            print(f"\n{student['name']} ({student['student_id']}): 오류 발생")
            print(f"  {result['error']}")
        else:
            total = result['total']
            success = result['success']
            failed = result['failed']
            success_rate = (success / total * 100) if total > 0 else 0

            print(f"\n{student['name']} ({student['student_id']}):")
            print(f"  성공: {success}/{total} ({success_rate:.1f}%)")
            print(f"  실패: {failed}/{total}")

            if failed > 0:
                print(f"  실패한 이미지:")
                for detail in result['details']:
                    if detail['status'] == "✗":
                        error_msg = detail['result'].get('error', 'Unknown error')
                        print(f"    - {detail['image']}: {error_msg}")

    print("\n" + "="*70)


def save_results(results: List[Dict], output_file: Path):
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n결과가 저장되었습니다: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='학생 API 서버로 이미지를 자동 전송하는 도구'
    )

    parser.add_argument(
        '--image-folder',
        type=Path,
        default=config.DEFAULT_IMAGE_FOLDER,
        help=f'이미지 폴더 경로 (기본: {config.DEFAULT_IMAGE_FOLDER})'
    )

    parser.add_argument(
        '--student-file',
        type=Path,
        default=config.DEFAULT_STUDENT_FILE,
        help=f'학생 API 목록 파일 (기본: {config.DEFAULT_STUDENT_FILE})'
    )

    parser.add_argument(
        '--interval',
        type=float,
        default=config.DEFAULT_INTERVAL,
        help=f'이미지 전송 간격 (초, 기본: {config.DEFAULT_INTERVAL})'
    )

    parser.add_argument(
        '--timeout',
        type=int,
        default=config.DEFAULT_TIMEOUT,
        help=f'API 요청 타임아웃 (초, 기본: {config.DEFAULT_TIMEOUT})'
    )

    parser.add_argument(
        '--parallel',
        action='store_true',
        help='여러 학생에게 병렬로 전송'
    )

    parser.add_argument(
        '--repeat',
        type=int,
        default=1,
        help='전송 반복 횟수 (기본: 1)'
    )

    parser.add_argument(
        '--output',
        type=Path,
        default=Path('send_results.json'),
        help='결과 저장 파일 (기본: send_results.json)'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='전송할 이미지 개수 제한 (기본: 전체)'
    )

    args = parser.parse_args()

    if not args.image_folder.exists():
        print(f"오류: 이미지 폴더를 찾을 수 없습니다: {args.image_folder}")
        sys.exit(1)

    if not args.student_file.exists():
        print(f"오류: 학생 API 파일을 찾을 수 없습니다: {args.student_file}")
        sys.exit(1)

    students = load_students(args.student_file)
    if not students:
        print("오류: 활성화된 학생 API가 없습니다.")
        sys.exit(1)

    images = load_images(args.image_folder)
    if not images:
        print(f"오류: 이미지를 찾을 수 없습니다: {args.image_folder}")
        sys.exit(1)

    if args.limit:
        images = images[:args.limit]

    print(f"="*70)
    print(f"이미지 전송 시작")
    print(f"="*70)
    print(f"이미지 폴더: {args.image_folder}")
    print(f"이미지 개수: {len(images)}개")
    print(f"학생 수: {len(students)}명")
    print(f"전송 간격: {args.interval}초")
    print(f"타임아웃: {args.timeout}초")
    print(f"반복 횟수: {args.repeat}회")
    print(f"병렬 모드: {'예' if args.parallel else '아니오'}")
    print(f"="*70)

    all_results = []

    for round_num in range(args.repeat):
        if args.repeat > 1:
            print(f"\n라운드 {round_num + 1}/{args.repeat}")

        if args.parallel:
            results = send_images_parallel(students, images, args.interval, args.timeout)
        else:
            results = []
            for student in students:
                result = send_images_to_student(student, images, args.interval, args.timeout)
                results.append(result)

        all_results.extend(results)

        if round_num < args.repeat - 1:
            print(f"\n다음 라운드까지 {args.interval}초 대기...\n")
            time.sleep(args.interval)

    print_summary(all_results)

    if args.output:
        save_results(all_results, args.output)


if __name__ == "__main__":
    main()
