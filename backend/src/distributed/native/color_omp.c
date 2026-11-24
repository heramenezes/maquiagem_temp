/*
 * Kernels paralelos a nível de dados (OpenMP) para conversão sRGB -> CIELAB (D65)
 * e distância de cor perceptual CIEDE2000 (Sharma et al., 2005).
 *
 * Portável entre Linux (GCC/Clang) e Windows (MSVC /openmp e MinGW-w64).
 * Nota: variáveis de laço OpenMP usam ptrdiff_t (inteiro com sinal) para
 * compatibilidade total com OpenMP 2.0 no MSVC (evita C3016).
 */

#include <math.h>
#include <stddef.h>
#include <stdint.h>

#ifdef _OPENMP
#include <omp.h>
#endif

#if defined(_WIN32) || defined(__CYGWIN__)
#define MTOM_EXPORT __declspec(dllexport)
#elif defined(__GNUC__) && __GNUC__ >= 4
#define MTOM_EXPORT __attribute__((visibility("default")))
#else
#define MTOM_EXPORT
#endif

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define DEG2RAD (M_PI / 180.0)
#define RAD2DEG (180.0 / M_PI)

static double g_srgb_lut[256];
static volatile int g_lut_ready = 0;

static void ensure_srgb_lut(void) {
    if (g_lut_ready) {
        return;
    }
    for (int i = 0; i < 256; ++i) {
        double c = (double)i / 255.0;
        g_srgb_lut[i] = (c <= 0.04045) ? (c / 12.92) : pow((c + 0.055) / 1.055, 2.4);
    }
    g_lut_ready = 1;
}

static inline void linear_rgb_to_lab_pixel(double r, double g, double b, float* out) {
    const double x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047;
    const double y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b);
    const double z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883;

    const double delta = 6.0 / 29.0;
    const double delta3 = delta * delta * delta;
    const double inv_3delta2 = 1.0 / (3.0 * delta * delta);
    const double offset = 4.0 / 29.0;

    const double fx = (x > delta3) ? cbrt(x) : (x * inv_3delta2 + offset);
    const double fy = (y > delta3) ? cbrt(y) : (y * inv_3delta2 + offset);
    const double fz = (z > delta3) ? cbrt(z) : (z * inv_3delta2 + offset);

    out[0] = (float)(116.0 * fy - 16.0);
    out[1] = (float)(500.0 * (fx - fy));
    out[2] = (float)(200.0 * (fy - fz));
}

MTOM_EXPORT int mtom_omp_max_threads(void) {
#ifdef _OPENMP
    return omp_get_max_threads();
#else
    return 1;
#endif
}

MTOM_EXPORT int mtom_has_openmp(void) {
#ifdef _OPENMP
    return 1;
#else
    return 0;
#endif
}

MTOM_EXPORT void mtom_rgb_u8_to_lab_f32(
    const uint8_t* rgb,
    float* out_lab,
    ptrdiff_t num_pixels
) {
    ensure_srgb_lut();
    ptrdiff_t i;
#ifdef _OPENMP
#pragma omp parallel for schedule(static) if (num_pixels >= 4096)
#endif
    for (i = 0; i < num_pixels; ++i) {
        const double r = g_srgb_lut[rgb[3 * i + 0]];
        const double g = g_srgb_lut[rgb[3 * i + 1]];
        const double b = g_srgb_lut[rgb[3 * i + 2]];
        linear_rgb_to_lab_pixel(r, g, b, &out_lab[3 * i]);
    }
}

MTOM_EXPORT void mtom_rgb_f64_to_lab_f32(
    const double* rgb,
    float* out_lab,
    ptrdiff_t num_pixels
) {
    ptrdiff_t i;
#ifdef _OPENMP
#pragma omp parallel for schedule(static) if (num_pixels >= 4096)
#endif
    for (i = 0; i < num_pixels; ++i) {
        const double cr = rgb[3 * i + 0];
        const double cg = rgb[3 * i + 1];
        const double cb = rgb[3 * i + 2];
        const double r = (cr <= 0.04045) ? (cr / 12.92) : pow((cr + 0.055) / 1.055, 2.4);
        const double g = (cg <= 0.04045) ? (cg / 12.92) : pow((cg + 0.055) / 1.055, 2.4);
        const double b = (cb <= 0.04045) ? (cb / 12.92) : pow((cb + 0.055) / 1.055, 2.4);
        linear_rgb_to_lab_pixel(r, g, b, &out_lab[3 * i]);
    }
}

static inline double pow7(double x) {
    const double x2 = x * x;
    const double x4 = x2 * x2;
    return x4 * x2 * x;
}

static inline double ciede2000_pair(
    double L1, double a1, double b1,
    double L2, double a2, double b2
) {
    const double C1 = hypot(a1, b1);
    const double C2 = hypot(a2, b2);
    const double C_bar = 0.5 * (C1 + C2);
    const double C_bar7 = pow7(C_bar);
    const double G = 0.5 * (1.0 - sqrt(C_bar7 / (C_bar7 + 6103515625.0)));

    const double a1p = (1.0 + G) * a1;
    const double a2p = (1.0 + G) * a2;
    const double C1p = hypot(a1p, b1);
    const double C2p = hypot(a2p, b2);

    double h1p = (b1 == 0.0 && a1p == 0.0) ? 0.0 : atan2(b1, a1p) * RAD2DEG;
    if (h1p < 0.0) {
        h1p += 360.0;
    }
    double h2p = (b2 == 0.0 && a2p == 0.0) ? 0.0 : atan2(b2, a2p) * RAD2DEG;
    if (h2p < 0.0) {
        h2p += 360.0;
    }

    const double dLp = L2 - L1;
    const double dCp = C2p - C1p;

    double dhp = 0.0;
    const double cprod = C1p * C2p;
    if (cprod != 0.0) {
        dhp = h2p - h1p;
        if (dhp > 180.0) {
            dhp -= 360.0;
        } else if (dhp < -180.0) {
            dhp += 360.0;
        }
    }
    const double dHp = 2.0 * sqrt(cprod) * sin(0.5 * dhp * DEG2RAD);

    const double Lp_bar = 0.5 * (L1 + L2);
    const double Cp_bar = 0.5 * (C1p + C2p);

    double hp_bar;
    if (cprod == 0.0) {
        hp_bar = h1p + h2p;
    } else if (fabs(h1p - h2p) <= 180.0) {
        hp_bar = 0.5 * (h1p + h2p);
    } else if (h1p + h2p < 360.0) {
        hp_bar = 0.5 * (h1p + h2p + 360.0);
    } else {
        hp_bar = 0.5 * (h1p + h2p - 360.0);
    }

    const double T = 1.0
        - 0.17 * cos((hp_bar - 30.0) * DEG2RAD)
        + 0.24 * cos((2.0 * hp_bar) * DEG2RAD)
        + 0.32 * cos((3.0 * hp_bar + 6.0) * DEG2RAD)
        - 0.20 * cos((4.0 * hp_bar - 63.0) * DEG2RAD);

    const double h_shift = (hp_bar - 275.0) / 25.0;
    const double dTheta = 30.0 * exp(-(h_shift * h_shift));
    const double Cp_bar7 = pow7(Cp_bar);
    const double RC = 2.0 * sqrt(Cp_bar7 / (Cp_bar7 + 6103515625.0));

    const double Lm50 = Lp_bar - 50.0;
    const double Lm50_2 = Lm50 * Lm50;
    const double SL = 1.0 + (0.015 * Lm50_2) / sqrt(20.0 + Lm50_2);
    const double SC = 1.0 + 0.045 * Cp_bar;
    const double SH = 1.0 + 0.015 * Cp_bar * T;
    const double RT = -sin(2.0 * dTheta * DEG2RAD) * RC;

    const double rL = dLp / SL;
    const double rC = dCp / SC;
    const double rH = dHp / SH;
    const double sq = rL * rL + rC * rC + rH * rH + RT * rC * rH;
    return (sq > 0.0) ? sqrt(sq) : 0.0;
}

MTOM_EXPORT void mtom_ciede2000_one_to_many_f64(
    const double* lab_ref,
    const double* lab_targets,
    double* out_de,
    ptrdiff_t count
) {
    const double L1 = lab_ref[0];
    const double a1 = lab_ref[1];
    const double b1 = lab_ref[2];
    ptrdiff_t i;
#ifdef _OPENMP
#pragma omp parallel for schedule(static) if (count >= 2048)
#endif
    for (i = 0; i < count; ++i) {
        out_de[i] = ciede2000_pair(
            L1, a1, b1,
            lab_targets[3 * i + 0],
            lab_targets[3 * i + 1],
            lab_targets[3 * i + 2]
        );
    }
}
