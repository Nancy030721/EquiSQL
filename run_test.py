import sys
from main import run_equivalence_check
import time

# Define test cases (command arguments + expectation)
GENERAL_TESTS = [
    # basic tests
    (["test/create-table.sql", "test/query1.sql", "test/query2.sql"], "counterexample"),
    (["test/create-table2.sql", "test/query3.sql", "test/query4.sql"], "EQUIVALENT"),
    # python main.py test/create-table2.sql test/query3.sql test/query4.sql -z3
   
    # tests on joins
    # python main.py test/create-table.sql test/join/inner_join.sql test/join/inner_join2.sql -z3
    (["test/create-table.sql", "test/join/inner_join.sql", "test/join/inner_join2.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/join/left_join.sql", "test/join/left_join2.sql"], "counterexample"),
    (["test/create-table.sql", "test/join/left_join2.sql", "test/join/cartisian_product.sql"], "counterexample"), 
    (["test/create-table.sql", "test/join/left_join3.sql", "test/join/right_join2.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/join/full_join.sql",  "test/join/full_join2.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/join/inner_join3.sql", "test/join/full_join3.sql"], "EQUIVALENT"),
    

    # tests on NULL and NOT NULL
    (["test/create-table.sql", "test/null/null3.sql", "test/null/null4.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/null/null5.sql", "test/null/null6.sql"], "counterexample"),
    (["test/null/create-table3.sql", "test/null/null7.sql",  "test/null/null8.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/null/null9.sql",  "test/null/null10.sql"], "counterexample"),
    (["test/null/create-table3.sql", "test/null/null11.sql",  "test/null/null12.sql"], "EQUIVALENT"), #new added
     (["test/null/create-table3.sql", "test/null/null13.sql",  "test/null/null14.sql"], "EQUIVALENT"), #new added
   
]


Z3_TESTS = [
    (["test/create-table.sql", "test/foo1.sql", "test/foo2.sql"], "EQUIVALENT"),
]

def run_test(args, expected, solver):
    try:
        start = time.perf_counter()
        result = run_equivalence_check(args[0], args[1], args[2], solver, test=True)
        end = time.perf_counter()
    except Exception as e:
        print(f"Execution error: {e}")
        return False, float('inf')

    if str(result).startswith(expected):
        print(f"PASS: {' '.join(args)}, runtime: {end-start:.5f}s")
        return True, end-start
    else:
        print(f"FAIL: {' '.join(args)}")
        print(f"   Expected output: {expected}")
        print(f"   Output was: {result}")
        if solver == "cvc5":
            print(f"   command line: python main.py {args[0]} {args[1]} {args[2]} -cvc5")
        else: 
            print(f"   command line: python main.py {args[0]} {args[1]} {args[2]} -z3")
        return False, float('inf')
    

if __name__ == "__main__":

    solver_type = "z3"
    if (len(sys.argv) == 2) and (sys.argv[1].lower() == "-cvc5") :
        solver_type = "cvc5"
    passed, passed_time = 0, 0

    print(f"\nRunning tests in {solver_type.upper()}...\n" + "="*60)

    if solver_type == "z3":
        test_num = len(GENERAL_TESTS) + len(Z3_TESTS)
        for args, expected in GENERAL_TESTS + Z3_TESTS: 
            result, t = run_test(args, expected, "z3")
            if result: 
                passed += 1 
                passed_time += t
    
    if solver_type == "cvc5":
        test_num = len(GENERAL_TESTS)
        for args, expected in GENERAL_TESTS: 
            result, t = run_test(args, expected, "cvc5")
            if result: 
                passed += 1 
                passed_time += t


    print("="*60)
    print(f"\nSUMMARY: {passed}/{test_num} tests passed")
    if passed > 0:
        print(f"Average runtime over successful (equivalent) tests: {passed_time / passed:.5f}s\n")
