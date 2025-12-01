import subprocess
import sys
from main import run_equivalence_check

# Define test cases (command arguments + expectation)
GENERAL_TESTS = [
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


Z3_TESTS = [
    (["test/create-table.sql", "test/foo1.sql", "test/foo2.sql"], "EQUIVALENT"),
]

def run_test_z3(args, expected):
    try:
        result = run_equivalence_check(args[0], args[1], args[2], "z3", test=True)
    except Exception as e:
        print(f"Execution error: {e}")
        return False

    if str(result).startswith(expected):
        print(f"PASS: {' '.join(args)}")
        return True
    else:
        print(f"FAIL: {' '.join(args)}")
        print(f"   Expected output: {expected}")
        print(f"   Output was: {result}")
        print(f"   command line: python main.py {args[0]} {args[1]} {args[2]}")
        return False



def run_test_cvc5(args, expected):
    try:
        result = run_equivalence_check(args[0], args[1], args[2], "cvc5", test=True)
    except Exception as e:
        print(f"FAIL: {' '.join(args)}")
        print(f"Execution error: {e} when running: python main.py {args[0]} {args[1]} {args[2]} -cvc5")
        return False

    if str(result).startswith(expected):
        print(f"PASS: {' '.join(args)}")
        return True
    else:
        print(f"FAIL: {' '.join(args)}")
        print(f"   Expected output: {expected}")
        print(f"   Output was: {result}")
        print(f"   command line: python main.py {args[0]} {args[1]} {args[2]} -cvc5")
        return False
    

if __name__ == "__main__":
    # print(sys.argv)
    solver_type = "z3"
    if (len(sys.argv) == 2) and (sys.argv[1].lower() == "-cvc5") :
        solver_type = "cvc5"
    passed = 0

    print("\nRunning tests...\n" + "="*60)

    test_num = len(GENERAL_TESTS)
    for args, expected in GENERAL_TESTS:
        if (solver_type == "z3" and run_test_z3(args, expected)) or (solver_type == "cvc5" and run_test_cvc5(args, expected)):
            passed += 1

    if (solver_type == "z3") :
        test_num += len(Z3_TESTS)
        for args, expected in Z3_TESTS:
            if (run_test_z3(args, expected)):
                passed += 1

    print("="*60)
    print(f"\nSUMMARY: {passed}/{test_num} tests passed.\n")
