// OJ SPJ contract: argv[1] is input, argv[2] is contestant output.
// Return 0 for AC, 1 for WA, and 2 for an invalid checker invocation/input.
#include <charconv>
#include <cstdint>
#include <fstream>
#include <numeric>
#include <string>
#include <system_error>

using u64 = std::uint64_t;
using u128 = unsigned __int128;

static u64 power_mod(u64 base, u64 exponent, u64 modulus) {
    u64 result = 1;
    while (exponent != 0) {
        if ((exponent & 1) != 0) {
            result = static_cast<u128>(result) * base % modulus;
        }
        base = static_cast<u128>(base) * base % modulus;
        exponent >>= 1;
    }
    return result;
}

static bool is_prime(u64 value) {
    if (value < 2) {
        return false;
    }
    for (u64 prime : {2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37}) {
        if (value % prime == 0) {
            return value == prime;
        }
    }

    u64 odd_part = value - 1;
    unsigned twos = 0;
    while ((odd_part & 1) == 0) {
        odd_part >>= 1;
        ++twos;
    }
    // Deterministic for uint64_t; avoids trial division up to sqrt(x) for
    // valid large answers such as (n + 1)^2 with n up to 10^9.
    // Forisek/Jancina, Theorem 3: https://ceur-ws.org/Vol-1326/020-Forisek.pdf
    for (u64 base : {2ULL, 325ULL, 9375ULL, 28178ULL, 450775ULL,
                     9780504ULL, 1795265022ULL}) {
        base %= value;
        if (base == 0) {
            continue;
        }
        u64 residue = power_mod(base, odd_part, value);
        if (residue == 1 || residue == value - 1) {
            continue;
        }
        bool reaches_minus_one = false;
        for (unsigned round = 1; round < twos; ++round) {
            residue = static_cast<u128>(residue) * residue % value;
            if (residue == value - 1) {
                reaches_minus_one = true;
                break;
            }
        }
        if (!reaches_minus_one) {
            return false;
        }
    }
    return true;
}

int main(int argc, char **argv) {
    if (argc != 3) {
        return 2;
    }
    // Keep both files separate. freopen on stdout neither reads contestant
    // answers through cin nor fits the read-only c_cpp syscall policy.
    std::ifstream input(argv[1]);
    std::ifstream output(argv[2]);
    if (!input || !output) {
        return 2;
    }

    int count;
    if (!(input >> count) || count < 1 || count > 100000) {
        return 2;
    }
    for (int index = 0; index < count; ++index) {
        u64 n;
        if (!(input >> n) || n < 2 || n > 1000000000) {
            return 2;
        }
        std::string token;
        if (!(output >> token)) {
            return 1;
        }
        const char *begin = token.data();
        const char *end = begin + token.size();
        if (*begin == '+') {
            ++begin;
        }
        u64 answer = 0;
        auto parsed = std::from_chars(begin, end, answer);
        if (parsed.ec != std::errc() || parsed.ptr != end || answer <= 1 ||
                std::gcd(answer, n) != 1 || is_prime(answer)) {
            return 1;
        }
    }

    std::string extra;
    if (input >> extra || !input.eof()) {
        return 2;
    }
    return (output >> extra || !output.eof()) ? 1 : 0;
}
