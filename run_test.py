import subprocess
import sys
from main import run_equivalence_check

# Define test cases (command arguments + expectation)
TESTS = [
    # basic tests
    (["test/create-table.sql", "test/query1.sql", "test/query2.sql"], "counterexample"),
    (["test/create-table2.sql", "test/query3.sql", "test/query4.sql"], "EQUIVALENT"),

    # tests on joins
    (["test/create-table.sql", "test/join/inner_join.sql", "test/join/inner_join2.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/join/left_join.sql", "test/join/left_join2.sql"], "counterexample"),
    (["test/create-table.sql", "test/join/left_join3.sql", "test/join/right_join2.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/join/full_join.sql",  "test/join/full_join2.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/join/inner_join3.sql", "test/join/full_join3.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/join/inner_join3.sql", "test/join/full_join4.sql"], "counterexample"),

    # tests on NULL and NOT NULL
    (["test/create-table.sql", "test/null/null1.sql", "test/null/null2.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/null/null3.sql", "test/null/null4.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/null/null5.sql", "test/null/null6.sql"], "EQUIVALENT"),
    (["test/null/create-table3.sql", "test/null/null7.sql",  "test/null/null8.sql"], "EQUIVALENT"),
]


def run_test(args, expected):
    try:
        result = run_equivalence_check(args[0], args[1], args[2], test=True)
    except Exception as e:
        print(f"Execution error: {e}")
        return False

    # output = result.stdout.strip() + "\n" + result.stderr.strip()
    # output = output.lower()
    # result = str(result)
    if str(result).startswith(expected):
        print(f"PASS: {' '.join(args)}")
        return True
    else:
        print(f"FAIL: {' '.join(args)}")
        print(f"   Expected output: {expected}")
        print(f"   Output was: {result}")
        print(f"   command line: python main.py {args[0]} {args[1]} {args[2]}")
        return False


if __name__ == "__main__":
    passed = 0

    print("\nRunning tests...\n" + "="*60)

    for args, expected in TESTS:
        if run_test(args, expected):
            passed += 1

    print("="*60)
    print(f"\nSUMMARY: {passed}/{len(TESTS)} tests passed.\n")

    if passed != len(TESTS):
        sys.exit(1)
