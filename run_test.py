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

    # tests on Aggregation - COUNT
    (["test/create-table.sql", "test/aggregate/count/count_test1.sql", "test/aggregate/count/count_test2.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/aggregate/count/count_diff1.sql", "test/aggregate/count/count_diff2.sql"], "counterexample"),
    (["test/create-table.sql", "test/aggregate/count/count_join1.sql", "test/aggregate/count/count_join2.sql"], "EQUIVALENT"),
    # Note: count_col_join tests skipped - they compare different columns (sid vs id)
    # python main.py test/create-table.sql test/aggregate/count/count_col_join1a.sql test/aggregate/count/count_col_join1b.sql
    (["test/create-table.sql", "test/aggregate/count/count_col_join1a.sql", "test/aggregate/count/count_col_join1b.sql"], "counterexample"),
    (["test/null/create-table3.sql", "test/aggregate/count/count1.sql", "test/aggregate/count/count2.sql"], "EQUIVALENT"),
    (["test/null/create-table3.sql", "test/aggregate/count/count1.sql", "test/aggregate/count/count3.sql"], "counterexample"),

    # tests on Aggregation - SUM
    # Basic equivalence tests
    (["test/create-table.sql", "test/aggregate/sum/sum_col1a.sql", "test/aggregate/sum/sum_col1b.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/aggregate/sum/sum_col2a.sql", "test/aggregate/sum/sum_col2b.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/aggregate/sum/sum_real1a.sql", "test/aggregate/sum/sum_real1b.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/aggregate/sum/sum_where1a.sql", "test/aggregate/sum/sum_where1b.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/aggregate/sum/sum_join1.sql", "test/aggregate/sum/sum_join2.sql"], "EQUIVALENT"),
    # Non-equivalence tests
    (["test/create-table.sql", "test/aggregate/sum/sum_diff1.sql", "test/aggregate/sum/sum_diff2.sql"], "counterexample"),

    # All these tests run after making some small changes to them. The sanity checker used to reject them for two reasons:
    # 1.it checks output schema match, so "COUNT(id)" and "COUNT(sid)" would not match, but "COUNT(id) as cnt" and "COUNT(sid) as cnt" is fine. 
    #   -- fix: this is the desired behavior, so I added output attribute aliasing in those test cases
    # 2.we convert COUNT, SUM, AVG into different strings, so the sanity checker would reject when see "SUM" VS "AVG"
    #   -- fix: for those with attribute aliasing, if their name match, skip and simply pass that to the encoder
    #           if their name doesn't match, reject 
    #.          for those without attribute aliasing, directly convert them into string and compare
    (["test/create-table.sql", "test/aggregate/sum/sum_null1.sql", "test/aggregate/sum/sum_null2.sql"], "counterexample"),
    (["test/null/create-table3.sql", "test/aggregate/sum/sum_null3a.sql", "test/aggregate/sum/sum_null3b.sql"], "EQUIVALENT"),
    (["test/create-table.sql", "test/aggregate/sum/sum_left_join1a.sql", "test/aggregate/sum/sum_left_join1b.sql"], "counterexample"),
    (["test/create-table.sql", "test/aggregate/count/count_col2b.sql", "test/aggregate/sum/sum_vs_count.sql"], "counterexample"),
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
        if solver == "cvc5":
            print(f"   command line: python main.py {args[0]} {args[1]} {args[2]} -cvc5")
        else:
            print(f"   command line: python main.py {args[0]} {args[1]} {args[2]} -z3")
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
