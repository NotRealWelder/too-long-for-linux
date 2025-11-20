#!/usr/bin/env python3
"""
Проверка длинных путей и имен файлов для Linux с учетом системных ограничений
"""

import argparse
import os
import sys


class Colors:
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def count_bytes(string):
    return len(string.encode("utf-8"))


def scan_directory(directory, show_progress=True):
    problems = []
    total_count = 0

    if show_progress:
        print("Подсчет файлов...", end=" ", flush=True)
        for root, dirs, files in os.walk(directory):
            total_count += len(dirs) + len(files)
        print(f"найдено: {total_count}")

    current_count = 0

    for root, dirs, files in os.walk(directory):
        for dir_name in dirs:
            current_count += 1
            full_path = os.path.join(root, dir_name)

            name_bytes = count_bytes(dir_name)
            if name_bytes > 255:
                problems.append(("DIR_NAME", name_bytes, full_path))

            path_bytes = count_bytes(full_path)
            if path_bytes > 4096:
                problems.append(("DIR_PATH", path_bytes, full_path))

            if show_progress and current_count % 100 == 0:
                progress = (current_count / total_count) * 100
                print(
                    f"\rСканирование: {progress:.1f}% ({current_count}/{total_count})",
                    end="",
                    flush=True,
                )

        for file_name in files:
            current_count += 1
            full_path = os.path.join(root, file_name)

            name_bytes = count_bytes(file_name)
            if name_bytes >= 255:
                problems.append(("FILE_NAME", name_bytes, full_path))

            path_bytes = count_bytes(full_path)
            if path_bytes >= 4096:
                problems.append(("FILE_PATH", path_bytes, full_path))

            if show_progress and current_count % 100 == 0:
                progress = (current_count / total_count) * 100
                print(
                    f"\rСканирование: {progress:.1f}% ({current_count}/{total_count})",
                    end="",
                    flush=True,
                )

    if show_progress:
        print(f"\rСканирование: 100.0% ({current_count}/{current_count})")

    return problems, current_count


def main():
    class RussianFormatter(argparse.RawDescriptionHelpFormatter):
        def __init__(self, prog):
            super().__init__(prog, width=80, max_help_position=30)

        def add_usage(self, usage, actions, groups, prefix=None):
            if prefix is None:
                prefix = "Использование: "
            return super().add_usage(usage, actions, groups, prefix)

    parser = argparse.ArgumentParser(
        description="Проверка длинных путей и имен файлов для Linux",
        formatter_class=RussianFormatter,
        add_help=False,
    )

    parser.add_argument(
        "directory", nargs="?", default=".", help="Директория для проверки"
    )

    parser.add_argument(
        "-h",
        "--help",
        action="help",
        default=argparse.SUPPRESS,
        help="Показать это сообщение и выйти",
    )
    parser.add_argument(
        "-p", "--no-progress", action="store_true", help="Отключить индикатор прогресса"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Тихий режим (только цифры)"
    )
    parser.add_argument(
        "-l", "--log", metavar="ФАЙЛ", help="Сохранить результаты в указанный файл"
    )

    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"Ошибка: Директория '{args.directory}' не существует", file=sys.stderr)
        sys.exit(1)

    try:
        problems, total = scan_directory(args.directory, not args.no_progress)

        if args.log:
            with open(args.log, "w", encoding="utf-8") as f:
                for problem_type, length, path in problems:
                    if "NAME" in problem_type:
                        f.write(f"ДЛИННОЕ ИМЯ [{length}/255]: {path}\n")
                    else:
                        f.write(f"ДЛИННЫЙ ПУТЬ [{length}/4096]: {path}\n")

        if args.quiet:
            name_count = len([p for p in problems if "NAME" in p[0]])
            path_count = len([p for p in problems if "PATH" in p[0]])
            print(f"{name_count} {path_count} {total}")
        else:
            print(f"\n{Colors.BOLD}РЕЗУЛЬТАТЫ ПРОВЕРКИ:{Colors.RESET}")
            print(f"Всего проверено: {Colors.BLUE}{total}{Colors.RESET}")

            name_problems = [p for p in problems if "NAME" in p[0]]
            path_problems = [p for p in problems if "PATH" in p[0]]

            print(
                f"Длинных имен (>255 байт): {Colors.YELLOW}{len(name_problems)}{Colors.RESET}"
            )
            print(
                f"Длинных путей (>4096 байт): {Colors.YELLOW}{len(path_problems)}{Colors.RESET}"
            )

            if problems:
                print(f"\n{Colors.BOLD}ПРОБЛЕМНЫЕ ФАЙЛЫ И ДИРЕКТОРИИ:{Colors.RESET}")
                for problem_type, length, path in problems:
                    if "NAME" in problem_type:
                        print(f"  ДЛИННОЕ ИМЯ [{length}/255]: {path}")
                    else:
                        print(f"  ДЛИННЫЙ ПУТЬ [{length}/4096]: {path}")
            else:
                print(
                    f"\n{Colors.GREEN}Все пути и имена соответствуют ограничениям Linux{Colors.RESET}"
                )

            if args.log:
                print(
                    f"\n{Colors.BLUE}Подробный отчет сохранен в: {args.log}{Colors.RESET}"
                )

        sys.exit(0 if not problems else 1)

    except KeyboardInterrupt:
        print("\nПроверка прервана пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка при выполнении: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
