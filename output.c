#include <stdbool.h>
#include <stdio.h>

typedef struct {
    bool is_some;
    int value;
} OptionInt;

typedef struct {
    int *data;
    int len;
} IntArray;

static OptionInt option_some(int value) {
    return (OptionInt){ true, value };
}

static OptionInt option_none(void) {
    return (OptionInt){ false, 0 };
}

static bool option_is_some(OptionInt option) {
    return option.is_some;
}

static bool option_is_none(OptionInt option) {
    return !option.is_some;
}

static void print_bool(bool value) {
    printf("%s\n", value ? "true" : "false");
}

static void print_option(OptionInt option) {
    if (option.is_some) {
        printf("Some(%d)\n", option.value);
    } else {
        printf("None\n");
    }
}

static OptionInt find(IntArray arr, int target) {
    for (int i = 0; i < arr.len; ++i) {
        int x = arr.data[i];
        if (x > target) {
            return option_some(x);
        }
    }
    return option_none();
}

static int mini_double(int x) {
    return x * 2;
}

typedef struct { int a; } add_closure;
static add_closure add(int a) {
    return (add_closure){ a };
}
static int add_apply(add_closure closure, int b) {
    return closure.a + b;
}

static int triple(int x) {
    return x * 3;
}

int main(void) {
    OptionInt x = option_some(10);
    OptionInt y = option_none();
    print_bool(option_is_some(x));
    print_bool(option_is_none(y));
    OptionInt a = option_some(10);
    int matched = a.is_some ? (a.value + 1) : (0);
    printf("%d\n", matched);
    int __arr0_data[] = { 1, 3, 5, 2, 4 };
    IntArray __arr0 = { __arr0_data, (int)(sizeof(__arr0_data) / sizeof(__arr0_data[0])) };
    OptionInt found = find(__arr0, 3);
    print_option(found);
    int __arr1_data[] = { 1, 2, 3 };
    IntArray __arr1 = { __arr1_data, (int)(sizeof(__arr1_data) / sizeof(__arr1_data[0])) };
    OptionInt missing = find(__arr1, 5);
    print_option(missing);
    printf("%d\n", mini_double(10));
    printf("%d\n", add_apply(add(3), 4));
    printf("%d\n", triple(7));
    return 0;
}
