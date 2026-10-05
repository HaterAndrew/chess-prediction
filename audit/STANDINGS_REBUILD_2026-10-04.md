# Standings rebuild: before and after, 2026-10-04

Before is `main` at fda97ce. After is the rebuilt `output/historical_standings.csv` on `feat/standings-data`. Both sides ran `06_walk_in_multipliers.py` and `04d_website_data_v2.py` locally on the same 2026-10-04 data.

## What changes on the site

- Standings rows: 195 before, 884 after (881 ccasite, 2 old scraper, 1 chessevents). The chessevents row is Pittsburgh Open 2026, read live by the repaired weekly scrape because cca-site lacks its Under 2100 section.
- Cards: 412. Point estimates moved on 0. The 17 live cards do not change: the walk-in multiplier applies only after an event starts.
- Grading (`perf/`, `04e_performance_data.py`) does not read the walk-in totals, so the performance page does not move.
- Complete cards: the total estimate moves on 29 of 31, median -6.4%, range -9.2% to +0.0%.
- Historical cards: the total estimate moves on 298 of 364, median -6.1%, range -34.7% to +0.0%.
- Walk-in families: 38 before, 48 after. Median family ratio 1.191 before, 0.975 after. Families with one usable edition: 37 before, 8 after.
- The model shrinks each family's ratio toward 1.1 by its number of editions (`model/walkins.py`), so a family at 0.97 over four editions applies about 1.04.

## Walk-in ratio per family

| Family | Before: median (editions) | After: median (editions) |
|---|---|---|
| Atlantic City Open | - | 0.951 (1) |
| Atlantic Open | 1.307 (1) | 0.984 (4) |
| Boston Chess Congress | 1.150 (1) | 0.978 (4) |
| Bradley Open | 1.159 (1) | 0.995 (4) |
| Central California Open | 1.229 (1) | 0.975 (4) |
| Central New York Open | 1.360 (1) | 1.000 (1) |
| Chicago Class | 1.245 (1) | 1.003 (4) |
| Chicago Open | - | 0.974 (4) |
| Cleveland Open | 1.256 (1) | 0.974 (4) |
| Continental Class | 1.162 (1) | 0.970 (1) |
| Continental Open | 1.283 (1) | 1.000 (4) |
| DC International | - | 0.953 (1) |
| DC Open | - | 0.973 (1) |
| Eastern Chess Congress | 1.189 (1) | 0.969 (3) |
| Eastern Class | 1.190 (1) | 0.969 (3) |
| Eastern Open | 2.281 (3) | 0.979 (3) |
| George Washington Open | 1.038 (1) | 0.977 (4) |
| Golden State Open | 1.121 (1) | 0.988 (4) |
| Hartford Open | 1.116 (1) | 0.951 (4) |
| Indianapolis Open | 1.267 (1) | 0.971 (4) |
| Kings Island Open | 1.073 (1) | 0.975 (3) |
| Liberty Bell Open | 1.218 (1) | 0.969 (4) |
| Los Angeles Open | 1.181 (1) | 0.971 (3) |
| Mid-America Open | 1.335 (1) | 0.980 (4) |
| Midwest Class Championships | 1.183 (1) | 0.958 (3) |
| National Chess Congress | - | 0.977 (3) |
| New York State Championship | 1.181 (1) | 0.991 (4) |
| New York State High School Championship | 1.192 (1) | 0.955 (2) |
| New York State Open | 1.193 (1) | 1.000 (3) |
| New York State Scholastic Championships | - | 0.806 (2) |
| New York State Scholastic Championships Grades K-8 | 0.972 (1) | 0.960 (2) |
| New York State Senior Championship With Young Adult Mi | 1.049 (1) | 0.966 (2) |
| Niagara Falls Open | 1.146 (1) | 0.994 (3) |
| North American Open | 1.311 (1) | 0.976 (3) |
| Open at Foxwoods | 1.103 (1) | 0.991 (2) |
| Pacific Coast Open | 1.146 (1) | 0.975 (4) |
| Philadelphia International | 0.968 (1) | 0.917 (3) |
| Philadelphia Open | 1.234 (1) | 0.969 (3) |
| Pittsburgh Open | 1.217 (1) | 0.974 (4) |
| Princeton Open | 1.286 (1) | 0.972 (1) |
| Southern Class | - | 0.997 (4) |
| Southern Open | 1.261 (1) | 0.990 (4) |
| Southwest Class Championships | 1.236 (1) | 0.967 (4) |
| Washington Chess Congress | 1.241 (1) | 0.976 (1) |
| Western Class | - | 0.983 (1) |
| Western Class Championships | 1.038 (1) | 0.976 (3) |
| World Open lower sections | - | 0.943 (4) |
| World Open top 6 sections | - | 0.983 (4) |

## Card totals that change

| Edition | Status | Point | Total before | Total after | Change | Multiplier before | after |
|---|---|---:|---:|---:|---:|---:|---:|
| Atlantic City Open 2019 | historical | 415 | 457 | 444 | -2.8% | 1.1 | 1.07 |
| Atlantic City Open 2022 | historical | 472 | 519 | 505 | -2.7% | 1.1 | 1.07 |
| Atlantic City Open 2023 | historical | 445 | 490 | 476 | -2.9% | 1.1 | 1.07 |
| Atlantic City Open 2024 | historical | 465 | 512 | 498 | -2.7% | 1.1 | 1.07 |
| Atlantic City Open 2025 | historical | 574 | 631 | 614 | -2.7% | 1.1 | 1.07 |
| Atlantic City Open 2026 | complete | 424 | 466 | 454 | -2.6% | 1.1 | 1.07 |
| Atlantic Open 2015 | historical | 226 | 258 | 235 | -8.9% | 1.141 | 1.042 |
| Atlantic Open 2016 | historical | 286 | 326 | 298 | -8.6% | 1.141 | 1.042 |
| Atlantic Open 2017 | historical | 283 | 323 | 295 | -8.7% | 1.141 | 1.042 |
| Atlantic Open 2018 | historical | 299 | 341 | 312 | -8.5% | 1.141 | 1.042 |
| Atlantic Open 2019 | historical | 289 | 330 | 301 | -8.8% | 1.141 | 1.042 |
| Atlantic Open 2022 | historical | 412 | 470 | 429 | -8.7% | 1.141 | 1.042 |
| Atlantic Open 2023 | historical | 371 | 423 | 387 | -8.5% | 1.141 | 1.042 |
| Atlantic Open 2024 | historical | 272 | 310 | 283 | -8.7% | 1.141 | 1.042 |
| Atlantic Open 2025 | historical | 238 | 272 | 248 | -8.8% | 1.141 | 1.042 |
| Atlantic Open 2026 | complete | 242 | 276 | 252 | -8.7% | 1.141 | 1.042 |
| Boston Chess Congress 2015 | historical | 225 | 250 | 234 | -6.4% | 1.11 | 1.039 |
| Boston Chess Congress 2016 | historical | 242 | 269 | 251 | -6.7% | 1.11 | 1.039 |
| Boston Chess Congress 2017 | historical | 208 | 231 | 216 | -6.5% | 1.11 | 1.039 |
| Boston Chess Congress 2018 | historical | 237 | 263 | 246 | -6.5% | 1.11 | 1.039 |
| Boston Chess Congress 2019 | historical | 270 | 300 | 281 | -6.3% | 1.11 | 1.039 |
| Boston Chess Congress 2022 | historical | 287 | 319 | 298 | -6.6% | 1.11 | 1.039 |
| Boston Chess Congress 2023 | historical | 391 | 434 | 406 | -6.5% | 1.11 | 1.039 |
| Boston Chess Congress 2024 | historical | 342 | 380 | 355 | -6.6% | 1.11 | 1.039 |
| Boston Chess Congress 2025 | historical | 383 | 425 | 398 | -6.4% | 1.11 | 1.039 |
| Boston Chess Congress 2026 | complete | 359 | 399 | 373 | -6.5% | 1.11 | 1.039 |
| Bradley Open 2015 | historical | 169 | 188 | 177 | -5.9% | 1.112 | 1.047 |
| Bradley Open 2016 | historical | 148 | 165 | 155 | -6.1% | 1.112 | 1.047 |
| Bradley Open 2017 | historical | 204 | 227 | 214 | -5.7% | 1.112 | 1.047 |
| Bradley Open 2018 | historical | 173 | 192 | 181 | -5.7% | 1.112 | 1.047 |
| Bradley Open 2019 | historical | 171 | 190 | 179 | -5.8% | 1.112 | 1.047 |
| Bradley Open 2022 | historical | 227 | 252 | 238 | -5.6% | 1.112 | 1.047 |
| Bradley Open 2023 | historical | 256 | 285 | 268 | -6.0% | 1.112 | 1.047 |
| Bradley Open 2024 | historical | 270 | 300 | 283 | -5.7% | 1.112 | 1.047 |
| Bradley Open 2025 | historical | 246 | 273 | 258 | -5.5% | 1.112 | 1.047 |
| Bradley Open 2026 | complete | 209 | 232 | 219 | -5.6% | 1.112 | 1.047 |
| Central California Open 2015 | historical | 114 | 128 | 118 | -7.8% | 1.126 | 1.037 |
| Central California Open 2016 | historical | 92 | 104 | 95 | -8.7% | 1.126 | 1.037 |
| Central California Open 2017 | historical | 150 | 169 | 156 | -7.7% | 1.126 | 1.037 |
| Central California Open 2018 | historical | 128 | 144 | 133 | -7.6% | 1.126 | 1.037 |
| Central California Open 2019 | historical | 128 | 144 | 133 | -7.6% | 1.126 | 1.037 |
| Central California Open 2022 | historical | 188 | 212 | 195 | -8.0% | 1.126 | 1.037 |
| Central California Open 2023 | historical | 214 | 241 | 222 | -7.9% | 1.126 | 1.037 |
| Central California Open 2024 | historical | 169 | 190 | 175 | -7.9% | 1.126 | 1.037 |
| Central California Open 2025 | historical | 179 | 202 | 186 | -7.9% | 1.126 | 1.037 |
| Central California Open 2026 | complete | 169 | 190 | 175 | -7.9% | 1.126 | 1.037 |
| Central New York Open 2015 | historical | 61 | 70 | 66 | -5.7% | 1.152 | 1.08 |
| Central New York Open 2016 | historical | 56 | 65 | 60 | -7.7% | 1.152 | 1.08 |
| Central New York Open 2017 | historical | 57 | 66 | 62 | -6.1% | 1.152 | 1.08 |
| Central New York Open 2018 | historical | 45 | 52 | 49 | -5.8% | 1.152 | 1.08 |
| Central New York Open 2019 | historical | 40 | 46 | 43 | -6.5% | 1.152 | 1.08 |
| Central New York Open 2022 | historical | 119 | 137 | 129 | -5.8% | 1.152 | 1.08 |
| Central New York Open 2023 | historical | 139 | 160 | 150 | -6.2% | 1.152 | 1.08 |
| Chicago Class 2015 | historical | 291 | 329 | 306 | -7.0% | 1.129 | 1.052 |
| Chicago Class 2016 | historical | 321 | 362 | 338 | -6.6% | 1.129 | 1.052 |
| Chicago Class 2017 | historical | 382 | 431 | 402 | -6.7% | 1.129 | 1.052 |
| Chicago Class 2018 | historical | 337 | 380 | 354 | -6.8% | 1.129 | 1.052 |
| Chicago Class 2019 | historical | 330 | 373 | 347 | -7.0% | 1.129 | 1.052 |
| Chicago Class 2022 | historical | 337 | 380 | 354 | -6.8% | 1.129 | 1.052 |
| Chicago Class 2023 | historical | 280 | 316 | 294 | -7.0% | 1.129 | 1.052 |
| Chicago Class 2024 | historical | 270 | 305 | 284 | -6.9% | 1.129 | 1.052 |
| Chicago Class 2025 | historical | 294 | 332 | 309 | -6.9% | 1.129 | 1.052 |
| Chicago Class 2026 | complete | 288 | 325 | 303 | -6.8% | 1.129 | 1.052 |
| Chicago Open 2015 | historical | 774 | 851 | 803 | -5.6% | 1.1 | 1.037 |
| Chicago Open 2016 | historical | 798 | 878 | 828 | -5.7% | 1.1 | 1.037 |
| Chicago Open 2017 | historical | 883 | 971 | 916 | -5.7% | 1.1 | 1.037 |
| Chicago Open 2018 | historical | 829 | 912 | 860 | -5.7% | 1.1 | 1.037 |
| Chicago Open 2019 | historical | 843 | 927 | 874 | -5.7% | 1.1 | 1.037 |
| Chicago Open 2022 | historical | 944 | 1038 | 979 | -5.7% | 1.1 | 1.037 |
| Chicago Open 2023 | historical | 960 | 1056 | 996 | -5.7% | 1.1 | 1.037 |
| Chicago Open 2024 | historical | 860 | 946 | 892 | -5.7% | 1.1 | 1.037 |
| Chicago Open 2025 | historical | 899 | 989 | 932 | -5.8% | 1.1 | 1.037 |
| Chicago Open 2026 | complete | 917 | 1009 | 951 | -5.7% | 1.1 | 1.037 |
| Cleveland Open 2015 | historical | 197 | 223 | 204 | -8.5% | 1.131 | 1.037 |
| Cleveland Open 2016 | historical | 190 | 215 | 197 | -8.4% | 1.131 | 1.037 |
| Cleveland Open 2017 | historical | 185 | 209 | 192 | -8.1% | 1.131 | 1.037 |
| Cleveland Open 2018 | historical | 196 | 222 | 203 | -8.6% | 1.131 | 1.037 |
| Cleveland Open 2019 | historical | 224 | 253 | 232 | -8.3% | 1.131 | 1.037 |
| Cleveland Open 2022 | historical | 201 | 227 | 208 | -8.4% | 1.131 | 1.037 |
| Cleveland Open 2023 | historical | 226 | 256 | 234 | -8.6% | 1.131 | 1.037 |
| Cleveland Open 2024 | historical | 167 | 189 | 173 | -8.5% | 1.131 | 1.037 |
| Cleveland Open 2025 | historical | 199 | 225 | 206 | -8.4% | 1.131 | 1.037 |
| Cleveland Open 2026 | complete | 179 | 202 | 186 | -7.9% | 1.131 | 1.037 |
| Continental Class 2023 | historical | 198 | 220 | 213 | -3.2% | 1.112 | 1.074 |
| Continental Open 2015 | historical | 253 | 288 | 266 | -7.6% | 1.137 | 1.05 |
| Continental Open 2016 | historical | 255 | 290 | 268 | -7.6% | 1.137 | 1.05 |
| Continental Open 2017 | historical | 350 | 398 | 368 | -7.5% | 1.137 | 1.05 |
| Continental Open 2018 | historical | 292 | 332 | 307 | -7.5% | 1.137 | 1.05 |
| Continental Open 2019 | historical | 274 | 311 | 288 | -7.4% | 1.137 | 1.05 |
| Continental Open 2022 | historical | 321 | 365 | 337 | -7.7% | 1.137 | 1.05 |
| Continental Open 2023 | historical | 312 | 355 | 328 | -7.6% | 1.137 | 1.05 |
| Continental Open 2024 | historical | 244 | 277 | 256 | -7.6% | 1.137 | 1.05 |
| Continental Open 2025 | historical | 265 | 301 | 278 | -7.6% | 1.137 | 1.05 |
| Continental Open 2026 | complete | 266 | 302 | 279 | -7.6% | 1.137 | 1.05 |
| DC International 2015 | historical | 128 | 141 | 137 | -2.8% | 1.1 | 1.071 |
| DC International 2016 | historical | 66 | 73 | 71 | -2.7% | 1.1 | 1.071 |
| DC International 2017 | historical | 87 | 96 | 93 | -3.1% | 1.1 | 1.071 |
| DC International 2018 | historical | 151 | 166 | 162 | -2.4% | 1.1 | 1.071 |
| DC International 2019 | historical | 147 | 162 | 157 | -3.1% | 1.1 | 1.071 |
| DC International 2022 | historical | 88 | 97 | 94 | -3.1% | 1.1 | 1.071 |
| DC International 2023 | historical | 108 | 119 | 116 | -2.5% | 1.1 | 1.071 |
| DC International 2024 | historical | 143 | 157 | 153 | -2.5% | 1.1 | 1.071 |
| DC International 2025 | historical | 126 | 139 | 135 | -2.9% | 1.1 | 1.071 |
| DC International 2026 | complete | 107 | 118 | 115 | -2.5% | 1.1 | 1.071 |
| DC Open 2015 | historical | 515 | 566 | 553 | -2.3% | 1.1 | 1.075 |
| DC Open 2016 | historical | 511 | 562 | 549 | -2.3% | 1.1 | 1.075 |
| DC Open 2017 | historical | 553 | 608 | 594 | -2.3% | 1.1 | 1.075 |
| DC Open 2018 | historical | 527 | 580 | 566 | -2.4% | 1.1 | 1.075 |
| DC Open 2019 | historical | 231 | 254 | 248 | -2.4% | 1.1 | 1.075 |
| DC Open 2022 | historical | 281 | 309 | 302 | -2.3% | 1.1 | 1.075 |
| DC Open 2023 | historical | 281 | 309 | 302 | -2.3% | 1.1 | 1.075 |
| DC Open 2024 | historical | 312 | 343 | 335 | -2.3% | 1.1 | 1.075 |
| DC Open 2025 | historical | 325 | 358 | 349 | -2.5% | 1.1 | 1.075 |
| DC Open 2026 | complete | 188 | 207 | 202 | -2.4% | 1.1 | 1.075 |
| Eastern Chess Congress 2015 | historical | 116 | 130 | 121 | -6.9% | 1.118 | 1.044 |
| Eastern Chess Congress 2016 | historical | 279 | 312 | 291 | -6.7% | 1.118 | 1.044 |
| Eastern Chess Congress 2017 | historical | 400 | 447 | 418 | -6.5% | 1.118 | 1.044 |
| Eastern Chess Congress 2018 | historical | 316 | 353 | 330 | -6.5% | 1.118 | 1.044 |
| Eastern Chess Congress 2019 | historical | 349 | 390 | 364 | -6.7% | 1.118 | 1.044 |
| Eastern Chess Congress 2022 | historical | 493 | 551 | 515 | -6.5% | 1.118 | 1.044 |
| Eastern Chess Congress 2023 | historical | 527 | 589 | 550 | -6.6% | 1.118 | 1.044 |
| Eastern Chess Congress 2024 | historical | 490 | 548 | 512 | -6.6% | 1.118 | 1.044 |
| Eastern Chess Congress 2025 | historical | 487 | 544 | 508 | -6.6% | 1.118 | 1.044 |
| Eastern Open 2022 | historical | 404 | 649 | 424 | -34.7% | 1.606 | 1.048 |
| Eastern Open 2023 | historical | 367 | 590 | 385 | -34.7% | 1.606 | 1.048 |
| Eastern Open 2024 | historical | 391 | 628 | 410 | -34.7% | 1.606 | 1.048 |
| Eastern Open 2025 | historical | 389 | 625 | 408 | -34.7% | 1.606 | 1.048 |
| George Washington Open 2016 | historical | 241 | 262 | 250 | -4.6% | 1.088 | 1.038 |
| George Washington Open 2017 | historical | 197 | 214 | 205 | -4.2% | 1.088 | 1.038 |
| George Washington Open 2018 | historical | 227 | 247 | 236 | -4.5% | 1.088 | 1.038 |
| George Washington Open 2019 | historical | 253 | 275 | 263 | -4.4% | 1.088 | 1.038 |
| George Washington Open 2023 | historical | 345 | 375 | 358 | -4.5% | 1.088 | 1.038 |
| George Washington Open 2024 | historical | 266 | 289 | 276 | -4.5% | 1.088 | 1.038 |
| George Washington Open 2025 | historical | 250 | 272 | 260 | -4.4% | 1.088 | 1.038 |
| George Washington Open 2026 | complete | 209 | 227 | 217 | -4.4% | 1.088 | 1.038 |
| Golden State Open 2015 | historical | 247 | 273 | 258 | -5.5% | 1.104 | 1.044 |
| Golden State Open 2016 | historical | 261 | 288 | 272 | -5.6% | 1.104 | 1.044 |
| Golden State Open 2017 | historical | 282 | 311 | 294 | -5.5% | 1.104 | 1.044 |
| Golden State Open 2018 | historical | 288 | 318 | 301 | -5.3% | 1.104 | 1.044 |
| Golden State Open 2019 | historical | 273 | 301 | 285 | -5.3% | 1.104 | 1.044 |
| Golden State Open 2022 | historical | 275 | 304 | 287 | -5.6% | 1.104 | 1.044 |
| Golden State Open 2023 | historical | 293 | 324 | 306 | -5.6% | 1.104 | 1.044 |
| Golden State Open 2024 | historical | 293 | 324 | 306 | -5.6% | 1.104 | 1.044 |
| Golden State Open 2025 | historical | 377 | 416 | 394 | -5.3% | 1.104 | 1.044 |
| Golden State Open 2026 | complete | 387 | 427 | 404 | -5.4% | 1.104 | 1.044 |
| Hartford Open 2015 | historical | 108 | 119 | 111 | -6.7% | 1.103 | 1.026 |
| Hartford Open 2016 | historical | 86 | 95 | 88 | -7.4% | 1.103 | 1.026 |
| Hartford Open 2017 | historical | 125 | 138 | 128 | -7.2% | 1.103 | 1.026 |
| Hartford Open 2018 | historical | 122 | 135 | 125 | -7.4% | 1.103 | 1.026 |
| Hartford Open 2019 | historical | 110 | 121 | 113 | -6.6% | 1.103 | 1.026 |
| Hartford Open 2022 | historical | 198 | 218 | 203 | -6.9% | 1.103 | 1.026 |
| Hartford Open 2023 | historical | 223 | 246 | 229 | -6.9% | 1.103 | 1.026 |
| Hartford Open 2024 | historical | 199 | 220 | 204 | -7.3% | 1.103 | 1.026 |
| Hartford Open 2025 | historical | 189 | 209 | 194 | -7.2% | 1.103 | 1.026 |
| Hartford Open 2026 | complete | 206 | 227 | 211 | -7.0% | 1.103 | 1.026 |
| Indianapolis Open 2015 | historical | 179 | 203 | 185 | -8.9% | 1.133 | 1.035 |
| Indianapolis Open 2016 | historical | 186 | 211 | 193 | -8.5% | 1.133 | 1.035 |
| Indianapolis Open 2017 | historical | 159 | 180 | 165 | -8.3% | 1.133 | 1.035 |
| Indianapolis Open 2018 | historical | 191 | 216 | 198 | -8.3% | 1.133 | 1.035 |
| Indianapolis Open 2019 | historical | 204 | 231 | 211 | -8.7% | 1.133 | 1.035 |
| Indianapolis Open 2022 | historical | 183 | 207 | 189 | -8.7% | 1.133 | 1.035 |
| Indianapolis Open 2023 | historical | 190 | 215 | 197 | -8.4% | 1.133 | 1.035 |
| Indianapolis Open 2024 | historical | 170 | 193 | 176 | -8.8% | 1.133 | 1.035 |
| Indianapolis Open 2025 | historical | 187 | 212 | 194 | -8.5% | 1.133 | 1.035 |
| Indianapolis Open 2026 | complete | 180 | 204 | 186 | -8.8% | 1.133 | 1.035 |
| Kings Island Open 2015 | historical | 274 | 300 | 287 | -4.3% | 1.095 | 1.046 |
| Kings Island Open 2016 | historical | 279 | 305 | 292 | -4.3% | 1.095 | 1.046 |
| Kings Island Open 2017 | historical | 291 | 319 | 304 | -4.7% | 1.095 | 1.046 |
| Kings Island Open 2018 | historical | 251 | 275 | 263 | -4.4% | 1.095 | 1.046 |
| Kings Island Open 2019 | historical | 298 | 326 | 312 | -4.3% | 1.095 | 1.046 |
| Kings Island Open 2022 | historical | 368 | 403 | 385 | -4.5% | 1.095 | 1.046 |
| Kings Island Open 2023 | historical | 358 | 392 | 375 | -4.3% | 1.095 | 1.046 |
| Kings Island Open 2024 | historical | 350 | 383 | 366 | -4.4% | 1.095 | 1.046 |
| Kings Island Open 2025 | historical | 356 | 390 | 372 | -4.6% | 1.095 | 1.046 |
| Liberty Bell Open 2015 | historical | 339 | 381 | 351 | -7.9% | 1.124 | 1.034 |
| Liberty Bell Open 2016 | historical | 326 | 366 | 337 | -7.9% | 1.124 | 1.034 |
| Liberty Bell Open 2017 | historical | 336 | 378 | 348 | -7.9% | 1.124 | 1.034 |
| Liberty Bell Open 2018 | historical | 334 | 375 | 346 | -7.7% | 1.124 | 1.034 |
| Liberty Bell Open 2019 | historical | 287 | 322 | 297 | -7.8% | 1.124 | 1.034 |
| Liberty Bell Open 2022 | historical | 362 | 407 | 374 | -8.1% | 1.124 | 1.034 |
| Liberty Bell Open 2023 | historical | 473 | 531 | 489 | -7.9% | 1.124 | 1.034 |
| Liberty Bell Open 2024 | historical | 481 | 540 | 498 | -7.8% | 1.124 | 1.034 |
| Liberty Bell Open 2025 | historical | 530 | 596 | 548 | -8.1% | 1.124 | 1.034 |
| Liberty Bell Open 2026 | complete | 564 | 634 | 583 | -8.0% | 1.124 | 1.034 |
| Los Angeles Open 2016 | historical | 171 | 191 | 179 | -6.3% | 1.116 | 1.045 |
| Los Angeles Open 2017 | historical | 213 | 238 | 223 | -6.3% | 1.116 | 1.045 |
| Los Angeles Open 2018 | historical | 252 | 281 | 263 | -6.4% | 1.116 | 1.045 |
| Los Angeles Open 2019 | historical | 241 | 269 | 252 | -6.3% | 1.116 | 1.045 |
| Los Angeles Open 2022 | historical | 361 | 403 | 377 | -6.5% | 1.116 | 1.045 |
| Los Angeles Open 2023 | historical | 415 | 463 | 434 | -6.3% | 1.116 | 1.045 |
| Los Angeles Open 2024 | historical | 412 | 460 | 430 | -6.5% | 1.116 | 1.045 |
| Los Angeles Open 2025 | historical | 397 | 443 | 415 | -6.3% | 1.116 | 1.045 |
| Mid-America Open 2015 | historical | 234 | 268 | 243 | -9.3% | 1.147 | 1.04 |
| Mid-America Open 2016 | historical | 210 | 241 | 218 | -9.5% | 1.147 | 1.04 |
| Mid-America Open 2017 | historical | 306 | 351 | 318 | -9.4% | 1.147 | 1.04 |
| Mid-America Open 2018 | historical | 268 | 307 | 279 | -9.1% | 1.147 | 1.04 |
| Mid-America Open 2019 | historical | 320 | 367 | 333 | -9.3% | 1.147 | 1.04 |
| Mid-America Open 2022 | historical | 288 | 330 | 300 | -9.1% | 1.147 | 1.04 |
| Mid-America Open 2023 | historical | 328 | 376 | 341 | -9.3% | 1.147 | 1.04 |
| Mid-America Open 2024 | historical | 305 | 350 | 317 | -9.4% | 1.147 | 1.04 |
| Mid-America Open 2025 | historical | 262 | 301 | 272 | -9.6% | 1.147 | 1.04 |
| Mid-America Open 2026 | complete | 200 | 229 | 208 | -9.2% | 1.147 | 1.04 |
| Midwest Class Championships 2015 | historical | 265 | 296 | 275 | -7.1% | 1.117 | 1.039 |
| Midwest Class Championships 2016 | historical | 280 | 313 | 291 | -7.0% | 1.117 | 1.039 |
| Midwest Class Championships 2017 | historical | 316 | 353 | 328 | -7.1% | 1.117 | 1.039 |
| Midwest Class Championships 2018 | historical | 328 | 366 | 341 | -6.8% | 1.117 | 1.039 |
| Midwest Class Championships 2019 | historical | 305 | 341 | 317 | -7.0% | 1.117 | 1.039 |
| Midwest Class Championships 2022 | historical | 360 | 402 | 374 | -7.0% | 1.117 | 1.039 |
| Midwest Class Championships 2023 | historical | 292 | 326 | 303 | -7.1% | 1.117 | 1.039 |
| Midwest Class Championships 2024 | historical | 303 | 338 | 315 | -6.8% | 1.117 | 1.039 |
| Midwest Class Championships 2025 | historical | 306 | 342 | 318 | -7.0% | 1.117 | 1.039 |
| National Chess Congress 2015 | historical | 574 | 631 | 601 | -4.8% | 1.1 | 1.047 |
| National Chess Congress 2016 | historical | 595 | 654 | 623 | -4.7% | 1.1 | 1.047 |
| National Chess Congress 2017 | historical | 645 | 710 | 676 | -4.8% | 1.1 | 1.047 |
| National Chess Congress 2018 | historical | 523 | 575 | 548 | -4.7% | 1.1 | 1.047 |
| National Chess Congress 2019 | historical | 550 | 605 | 576 | -4.8% | 1.1 | 1.047 |
| National Chess Congress 2022 | historical | 606 | 667 | 635 | -4.8% | 1.1 | 1.047 |
| National Chess Congress 2023 | historical | 636 | 700 | 666 | -4.9% | 1.1 | 1.047 |
| National Chess Congress 2024 | historical | 621 | 683 | 650 | -4.8% | 1.1 | 1.047 |
| National Chess Congress 2025 | historical | 705 | 776 | 738 | -4.9% | 1.1 | 1.047 |
| New York State Championship 2015 | historical | 173 | 193 | 181 | -6.2% | 1.116 | 1.045 |
| New York State Championship 2016 | historical | 190 | 212 | 199 | -6.1% | 1.116 | 1.045 |
| New York State Championship 2017 | historical | 183 | 204 | 191 | -6.4% | 1.116 | 1.045 |
| New York State Championship 2018 | historical | 188 | 210 | 197 | -6.2% | 1.116 | 1.045 |
| New York State Championship 2019 | historical | 185 | 206 | 193 | -6.3% | 1.116 | 1.045 |
| New York State Championship 2022 | historical | 316 | 353 | 330 | -6.5% | 1.116 | 1.045 |
| New York State Championship 2023 | historical | 347 | 387 | 363 | -6.2% | 1.116 | 1.045 |
| New York State Championship 2024 | historical | 326 | 364 | 341 | -6.3% | 1.116 | 1.045 |
| New York State Championship 2025 | historical | 348 | 388 | 364 | -6.2% | 1.116 | 1.045 |
| New York State Championship 2026 | complete | 332 | 371 | 347 | -6.5% | 1.116 | 1.045 |
| New York State High School Championship 2025 | historical | 219 | 245 | 230 | -6.1% | 1.118 | 1.052 |
| New York State High School Championship 2026 | complete | 198 | 221 | 208 | -5.9% | 1.118 | 1.052 |
| New York State Open 2015 | historical | 70 | 78 | 74 | -5.1% | 1.119 | 1.057 |
| New York State Open 2016 | historical | 100 | 112 | 106 | -5.4% | 1.119 | 1.057 |
| New York State Open 2017 | historical | 86 | 96 | 91 | -5.2% | 1.119 | 1.057 |
| New York State Open 2024 | historical | 76 | 85 | 80 | -5.9% | 1.119 | 1.057 |
| New York State Open 2025 | historical | 83 | 93 | 88 | -5.4% | 1.119 | 1.057 |
| New York State Open 2026 | complete | 109 | 122 | 115 | -5.7% | 1.119 | 1.057 |
| New York State Scholastic Championships Grades K-8 2015 | historical | 953 | 1024 | 1004 | -2.0% | 1.074 | 1.053 |
| New York State Scholastic Championships Grades K-8 2016 | historical | 952 | 1023 | 1003 | -2.0% | 1.074 | 1.053 |
| New York State Scholastic Championships Grades K-8 2017 | historical | 1156 | 1242 | 1218 | -1.9% | 1.074 | 1.053 |
| New York State Scholastic Championships Grades K-8 2018 | historical | 1229 | 1320 | 1295 | -1.9% | 1.074 | 1.053 |
| New York State Scholastic Championships Grades K-8 2019 | historical | 1249 | 1342 | 1316 | -1.9% | 1.074 | 1.053 |
| New York State Scholastic Championships Grades K-8 2022 | historical | 941 | 1011 | 991 | -2.0% | 1.074 | 1.053 |
| New York State Scholastic Championships Grades K-8 2023 | historical | 1548 | 1663 | 1631 | -1.9% | 1.074 | 1.053 |
| New York State Scholastic Championships Grades K-8 2024 | historical | 1777 | 1909 | 1872 | -1.9% | 1.074 | 1.053 |
| New York State Scholastic Championships Grades K-8 2025 | historical | 1767 | 1898 | 1861 | -1.9% | 1.074 | 1.053 |
| New York State Scholastic Championships Grades K-8 2026 | complete | 1753 | 1883 | 1846 | -2.0% | 1.074 | 1.053 |
| New York State Senior Championship With Young Adult Mi 2025 | historical | 57 | 62 | 60 | -3.2% | 1.09 | 1.055 |
| New York State Senior Championship With Young Adult Mi 2026 | complete | 61 | 66 | 64 | -3.0% | 1.09 | 1.055 |
| Niagara Falls Open 2022 | historical | 94 | 104 | 99 | -4.8% | 1.109 | 1.055 |
| Niagara Falls Open 2023 | historical | 170 | 189 | 179 | -5.3% | 1.109 | 1.055 |
| Niagara Falls Open 2024 | historical | 177 | 196 | 187 | -4.6% | 1.109 | 1.055 |
| Niagara Falls Open 2025 | historical | 123 | 136 | 130 | -4.4% | 1.109 | 1.055 |
| North American Open 2015 | historical | 717 | 819 | 751 | -8.3% | 1.142 | 1.047 |
| North American Open 2016 | historical | 766 | 875 | 802 | -8.3% | 1.142 | 1.047 |
| North American Open 2017 | historical | 800 | 914 | 838 | -8.3% | 1.142 | 1.047 |
| North American Open 2018 | historical | 822 | 939 | 861 | -8.3% | 1.142 | 1.047 |
| North American Open 2019 | historical | 863 | 986 | 904 | -8.3% | 1.142 | 1.047 |
| North American Open 2022 | historical | 1071 | 1223 | 1121 | -8.3% | 1.142 | 1.047 |
| North American Open 2023 | historical | 1115 | 1274 | 1167 | -8.4% | 1.142 | 1.047 |
| North American Open 2024 | historical | 1102 | 1259 | 1154 | -8.3% | 1.142 | 1.047 |
| North American Open 2025 | historical | 1256 | 1435 | 1315 | -8.4% | 1.142 | 1.047 |
| Pacific Coast Open 2015 | historical | 203 | 225 | 211 | -6.2% | 1.109 | 1.037 |
| Pacific Coast Open 2016 | historical | 214 | 237 | 222 | -6.3% | 1.109 | 1.037 |
| Pacific Coast Open 2017 | historical | 232 | 257 | 241 | -6.2% | 1.109 | 1.037 |
| Pacific Coast Open 2018 | historical | 245 | 272 | 254 | -6.6% | 1.109 | 1.037 |
| Pacific Coast Open 2019 | historical | 230 | 255 | 239 | -6.3% | 1.109 | 1.037 |
| Pacific Coast Open 2022 | historical | 344 | 382 | 357 | -6.5% | 1.109 | 1.037 |
| Pacific Coast Open 2023 | historical | 403 | 447 | 418 | -6.5% | 1.109 | 1.037 |
| Pacific Coast Open 2024 | historical | 361 | 400 | 375 | -6.2% | 1.109 | 1.037 |
| Pacific Coast Open 2025 | historical | 391 | 434 | 406 | -6.5% | 1.109 | 1.037 |
| Pacific Coast Open 2026 | complete | 394 | 437 | 409 | -6.4% | 1.109 | 1.037 |
| Pittsburgh Open 2015 | historical | 136 | 153 | 141 | -7.8% | 1.123 | 1.037 |
| Pittsburgh Open 2016 | historical | 106 | 119 | 110 | -7.6% | 1.123 | 1.037 |
| Pittsburgh Open 2017 | historical | 113 | 127 | 117 | -7.9% | 1.123 | 1.037 |
| Pittsburgh Open 2018 | historical | 130 | 146 | 135 | -7.5% | 1.123 | 1.037 |
| Pittsburgh Open 2019 | historical | 176 | 198 | 182 | -8.1% | 1.123 | 1.037 |
| Pittsburgh Open 2022 | historical | 195 | 219 | 202 | -7.8% | 1.123 | 1.037 |
| Pittsburgh Open 2023 | historical | 183 | 206 | 190 | -7.8% | 1.123 | 1.037 |
| Pittsburgh Open 2024 | historical | 166 | 186 | 172 | -7.5% | 1.123 | 1.037 |
| Pittsburgh Open 2025 | historical | 152 | 171 | 158 | -7.6% | 1.123 | 1.037 |
| Pittsburgh Open 2026 | complete | 170 | 191 | 176 | -7.9% | 1.123 | 1.037 |
| Southern Open 2015 | historical | 210 | 238 | 219 | -8.0% | 1.132 | 1.045 |
| Southern Open 2016 | historical | 203 | 230 | 212 | -7.8% | 1.132 | 1.045 |
| Southern Open 2017 | historical | 211 | 239 | 221 | -7.5% | 1.132 | 1.045 |
| Southern Open 2018 | historical | 231 | 262 | 241 | -8.0% | 1.132 | 1.045 |
| Southern Open 2019 | historical | 181 | 205 | 189 | -7.8% | 1.132 | 1.045 |
| Southern Open 2022 | historical | 266 | 301 | 278 | -7.6% | 1.132 | 1.045 |
| Southern Open 2023 | historical | 294 | 333 | 307 | -7.8% | 1.132 | 1.045 |
| Southern Open 2024 | historical | 231 | 262 | 241 | -8.0% | 1.132 | 1.045 |
| Southern Open 2025 | historical | 188 | 213 | 196 | -8.0% | 1.132 | 1.045 |
| Southern Open 2026 | complete | 206 | 233 | 215 | -7.7% | 1.132 | 1.045 |
| Southwest Class Championships 2015 | historical | 259 | 292 | 268 | -8.2% | 1.127 | 1.033 |
| Southwest Class Championships 2016 | historical | 298 | 336 | 308 | -8.3% | 1.127 | 1.033 |
| Southwest Class Championships 2017 | historical | 328 | 370 | 339 | -8.4% | 1.127 | 1.033 |
| Southwest Class Championships 2018 | historical | 355 | 400 | 367 | -8.2% | 1.127 | 1.033 |
| Southwest Class Championships 2019 | historical | 385 | 434 | 398 | -8.3% | 1.127 | 1.033 |
| Southwest Class Championships 2022 | historical | 397 | 447 | 410 | -8.3% | 1.127 | 1.033 |
| Southwest Class Championships 2023 | historical | 426 | 480 | 440 | -8.3% | 1.127 | 1.033 |
| Southwest Class Championships 2024 | historical | 441 | 497 | 456 | -8.2% | 1.127 | 1.033 |
| Southwest Class Championships 2025 | historical | 488 | 550 | 504 | -8.4% | 1.127 | 1.033 |
| Southwest Class Championships 2026 | complete | 492 | 555 | 508 | -8.5% | 1.127 | 1.033 |
| Washington Chess Congress 2015 | historical | 185 | 209 | 199 | -4.8% | 1.128 | 1.075 |
| Washington Chess Congress 2016 | historical | 197 | 222 | 212 | -4.5% | 1.128 | 1.075 |
| Washington Chess Congress 2017 | historical | 219 | 247 | 235 | -4.9% | 1.128 | 1.075 |
| Washington Chess Congress 2018 | historical | 235 | 265 | 253 | -4.5% | 1.128 | 1.075 |
| Washington Chess Congress 2019 | historical | 271 | 306 | 291 | -4.9% | 1.128 | 1.075 |
| Washington Chess Congress 2023 | historical | 249 | 281 | 268 | -4.6% | 1.128 | 1.075 |
| Western Class Championships 2015 | historical | 200 | 218 | 209 | -4.1% | 1.088 | 1.047 |
| Western Class Championships 2016 | historical | 202 | 220 | 211 | -4.1% | 1.088 | 1.047 |
| Western Class Championships 2017 | historical | 254 | 276 | 266 | -3.6% | 1.088 | 1.047 |
| Western Class Championships 2018 | historical | 245 | 266 | 257 | -3.4% | 1.088 | 1.047 |
| Western Class Championships 2019 | historical | 253 | 275 | 265 | -3.6% | 1.088 | 1.047 |
| Western Class Championships 2022 | historical | 362 | 394 | 379 | -3.8% | 1.088 | 1.047 |
| Western Class Championships 2023 | historical | 346 | 376 | 362 | -3.7% | 1.088 | 1.047 |
| Western Class Championships 2024 | historical | 421 | 458 | 441 | -3.7% | 1.088 | 1.047 |
| Western Class Championships 2025 | historical | 389 | 423 | 407 | -3.8% | 1.088 | 1.047 |
| Western Class Championships 2026 | complete | 318 | 346 | 333 | -3.8% | 1.088 | 1.047 |
| World Open lower sections 2023 | historical | 149 | 164 | 152 | -7.3% | 1.1 | 1.022 |
| World Open lower sections 2024 | historical | 151 | 166 | 154 | -7.2% | 1.1 | 1.022 |
| World Open lower sections 2025 | historical | 135 | 148 | 138 | -6.8% | 1.1 | 1.022 |
| World Open lower sections 2026 | complete | 93 | 102 | 95 | -6.9% | 1.1 | 1.022 |
| World Open top 6 sections 2023 | historical | 1324 | 1456 | 1379 | -5.3% | 1.1 | 1.041 |
| World Open top 6 sections 2024 | historical | 1195 | 1314 | 1244 | -5.3% | 1.1 | 1.041 |
| World Open top 6 sections 2025 | historical | 1165 | 1282 | 1213 | -5.4% | 1.1 | 1.041 |
| World Open top 6 sections 2026 | complete | 1066 | 1173 | 1110 | -5.4% | 1.1 | 1.041 |

## Import report

881 rows: 224 before 2009, 129 2009-2012, 528 2013 on.
119 editions in 59 folders outside the tracked families, not imported.
122 editions with no standings files.

Sections dropped: 1298 side event, 150 separate event, 10 schedule list, 6 team section, 3 re-lists other sections, 1 re-lists the 2024 field.

### Findings

- pittsburgh 2026: not imported, cca-site has no Under 2100 section; chessevents.com lists it with 40 players
- worldopen 2001: not imported, cca-site has 3 of the 8 main sections the March 2026 archive scrape found
- easternopen 2023: 'Senior Championship' (398 rows) re-lists the 2024 field; dropped
- DC International 2013: filed in dcinternational/2013, international/2013, one count; kept dcinternational
- DC International 2014: filed in dcinternational/2014, international/2014, one count; kept dcinternational
- DC International 2015: filed in dcinternational/2015, international/2015, one count; kept dcinternational
- Bostonchess Congress 2012: no rebuilt row; the committed row (164, old count rule) is kept
- World Open 2001: no rebuilt row; the committed row (1397, old count rule) is kept

### Against the summary's final count

499 rebuilt rows within 0.85-1.25 times the final count, 11 outside.

| Edition | Final count | New total | New / final |
|---|---:|---:|---:|
| New York State Scholastic Championships Grades K-8 2023 | 1548 | 1011 | 0.65 |
| Mid-America Open 2020 | 189 | 129 | 0.68 |
| Southern Class Championships 2021 | 146 | 106 | 0.73 |
| Chicago Open 2020 | 415 | 304 | 0.73 |
| Cleveland Open 2024 | 167 | 139 | 0.83 |
| DC International 2024 | 143 | 120 | 0.84 |
| Washington Chess Congress 2014 | 138 | 173 | 1.25 |
| New York State Open 2014 | 68 | 88 | 1.29 |
| Indianapolis Open 2012 | 161 | 210 | 1.30 |
| Manhattan Open 2012 | 281 | 401 | 1.43 |
| Empire State Open 2021 | 151 | 224 | 1.48 |

### Against the committed rows

193 paired, 0 equal, 2 within 2%, 2 with no rebuilt row.

No rebuilt row: Boston Chess Congress 2012; World Open top 6 sections 2001

| Edition | Old total | Old without side events | New total | New / old | Not in cca-site |
|---|---:|---:|---:|---:|---|
| Atlantic City Open 2009 | 1287 | 1241 | 573 | 0.45 | Tournament Standings (All Final) |
| Mid-America Open 2017 | 951 | 829 | 314 | 0.33 | 2010, 2009 |
| Western Class Championships 2019 | 900 | 783 | 274 | 0.30 | 2010, 2009 |
| Mid-America Open 2018 | 900 | 771 | 278 | 0.31 | 2010, 2009 |
| Mid-America Open 2019 | 949 | 826 | 329 | 0.35 | 2010, 2009 |
| Western Class Championships 2018 | 872 | 766 | 260 | 0.30 | 2010, 2009 |
| Western Class Championships 2015 | 809 | 709 | 207 | 0.26 | 2010, 2009 |
| Mid-America Open 2015 | 862 | 767 | 261 | 0.30 | 2010, 2009 |
| Mid-America Open 2016 | 819 | 745 | 231 | 0.28 | 2010, 2009 |
| Western Class Championships 2017 | 842 | 766 | 259 | 0.31 | 2010, 2009 |
| Mid-America Open 2014 | 838 | 750 | 259 | 0.31 | 2010, 2009 |
| Western Class Championships 2016 | 808 | 737 | 229 | 0.28 | 2010, 2009 |
| Western Class Championships 2014 | 793 | 713 | 215 | 0.27 | 2010, 2009 |
| Eastern Open 2023 | 877 | 763 | 359 | 0.41 | Senior Championship! |
| Eastern Open 2022 | 898 | 792 | 389 | 0.43 | Senior Champoionship! |
| Eastern Open 2025 | 887 | 780 | 381 | 0.43 | Senior Championship! |
| Eastern Open 2024 | 892 | 796 | 389 | 0.44 | Senior Championship! |
| Western Class Championships 2012 | 743 | 743 | 245 | 0.33 | 2010, 2009 |
| Western Class Championships 2013 | 730 | 730 | 232 | 0.32 | 2010, 2009 |
| Mid-America Open 2012 | 711 | 711 | 220 | 0.31 | 2010, 2009 |
| Mid-America Open 2013 | 753 | 753 | 262 | 0.35 | 2010, 2009 |
| Mid-America Open 2011 | 675 | 675 | 196 | 0.29 | 2010, 2009 |
| Western Class Championships 2011 | 685 | 685 | 227 | 0.33 | 2010, 2009 |
| North American Open 2025 | 1647 | 1243 | 1209 | 0.73 |  |
| Kings Island Open 2011 | 708 | 708 | 327 | 0.46 | Final Standings |
| Pacific Coast Open 2021 | 69 | 69 | 442 | 6.41 |  |
| Continental Open 2021 | 38 | 38 | 387 | 10.18 |  |
| Golden State Open 2012 | 600 | 600 | 280 | 0.47 | Final Standings |
| Midwest Class Championships 2021 | 45 | 45 | 360 | 8.00 |  |
| Los Angeles Open 2021 | 80 | 80 | 376 | 4.70 |  |
| Southwest Class Championships 2020 | 94 | 94 | 378 | 4.02 |  |
| DC Open 2018 | 837 | 614 | 572 | 0.68 |  |
| Kings Island Open 2021 | 59 | 59 | 324 | 5.49 |  |
| Mid-America Open 2010 | 449 | 449 | 185 | 0.41 | Other Tournaments, 2009 |
| Northeast Open 2022 | 474 | 438 | 216 | 0.46 | 3-Day Major!, 3-Day Under 2100, 3-Day Under 1800, 3-Day Under 1500, 3-Day Under 1200, 2-Day Major!, 2-Day Under 2100, 2-Day Under 1800, 2-Day Under 1500, 2-Day Under 1200 |
| Western Class Championships 2009 | 456 | 456 | 201 | 0.44 | Other Tournaments, 2010 |
| Western Class Championships 2010 | 456 | 456 | 208 | 0.46 | Other Tournaments, 2009 |
| DC Open 2014 | 813 | 619 | 571 | 0.70 |  |
| Atlantic City Open 2019 | 659 | 468 | 426 | 0.65 |  |
| Bradley Open 2021 | 59 | 59 | 290 | 4.92 |  |
| DC Open 2015 | 818 | 629 | 587 | 0.72 |  |
| Continental Open 2017 | 595 | 411 | 369 | 0.62 |  |
| DC Open 2016 | 779 | 595 | 553 | 0.71 |  |
| Golden State Open 2020 | 79 | 79 | 305 | 3.86 |  |
| Mid-America Open 2009 | 449 | 449 | 228 | 0.51 | Other Tournaments, 2010 |
| Southern Open 2011 | 400 | 400 | 180 | 0.45 | Standings |
| DC Open 2021 | 37 | 37 | 254 | 6.86 |  |
| DC Open 2017 | 818 | 647 | 605 | 0.74 |  |
| Southwest Class Championships 2018 | 561 | 415 | 355 | 0.63 |  |
| Midwest Class Championships 2017 | 530 | 385 | 333 | 0.63 |  |
| World Open top 6 sections 2002 | 1399 | 1399 | 1208 | 0.86 |  |
| Southwest Class Championships 2017 | 526 | 409 | 338 | 0.64 |  |
| George Washington Open 2020 | 70 | 70 | 254 | 3.63 |  |
| Atlantic City Open 2025 | 738 | 570 | 558 | 0.76 |  |
| Southwest Class Championships 2019 | 573 | 453 | 393 | 0.69 |  |
| Midwest Class Championships 2018 | 514 | 395 | 339 | 0.66 |  |
| Southwest Class Championships 2015 | 460 | 328 | 286 | 0.62 |  |
| Kings Island Open 2017 | 481 | 370 | 308 | 0.64 |  |
| Midwest Class Championships 2015 | 465 | 349 | 292 | 0.63 |  |
| Midwest Class Championships 2019 | 481 | 360 | 308 | 0.64 |  |
| Continental Open 2018 | 479 | 347 | 311 | 0.65 |  |
| Kings Island Open 2015 | 461 | 356 | 293 | 0.64 |  |
| Kings Island Open 2016 | 471 | 360 | 304 | 0.65 |  |
| Pacific Coast Open 2015 | 387 | 272 | 220 | 0.57 |  |
| Continental Open 2015 | 437 | 322 | 272 | 0.62 |  |
| Boston Chess Congress 2018 | 385 | 269 | 221 | 0.57 |  |
| Boston Chess Congress 2020 | 433 | 313 | 271 | 0.63 |  |
| Southwest Class Championships 2016 | 460 | 359 | 302 | 0.66 |  |
| Boston Chess Congress 2019 | 427 | 318 | 270 | 0.63 |  |
| Golden State Open 2016 | 423 | 327 | 270 | 0.64 |  |
| Western Class Championships 2020 | 37 | 37 | 190 | 5.14 |  |
| Cleveland Open 2021 | 54 | 54 | 206 | 3.81 |  |
| Golden State Open 2018 | 441 | 328 | 289 | 0.66 |  |
| Pacific Coast Open 2017 | 398 | 294 | 246 | 0.62 |  |
| Kings Island Open 2019 | 463 | 367 | 312 | 0.67 |  |
| Midwest Class Championships 2014 | 434 | 325 | 283 | 0.65 |  |
| Midwest Class Championships 2016 | 459 | 351 | 309 | 0.67 |  |
| Kings Island Open 2014 | 488 | 381 | 339 | 0.69 |  |
| Continental Open 2019 | 421 | 325 | 274 | 0.65 |  |
| George Washington Open 2016 | 387 | 277 | 242 | 0.63 |  |
| Cleveland Open 2019 | 378 | 280 | 235 | 0.62 |  |
| Los Angeles Open 2018 | 393 | 298 | 250 | 0.64 |  |
| Pacific Coast Open 2018 | 398 | 298 | 256 | 0.64 |  |
| George Washington Open 2019 | 401 | 294 | 260 | 0.65 |  |
| Liberty Bell Open 2026 | 687 | 566 | 546 | 0.79 |  |
| George Washington Open 2018 | 375 | 278 | 236 | 0.63 |  |
| Pacific Coast Open 2019 | 386 | 294 | 247 | 0.64 |  |
| Cleveland Open 2018 | 344 | 254 | 207 | 0.60 |  |
| Bradley Open 2017 | 345 | 241 | 209 | 0.61 |  |
| DC Open 2019 | 370 | 271 | 234 | 0.63 |  |
| Los Angeles Open 2019 | 377 | 290 | 241 | 0.64 |  |
| Golden State Open 2019 | 413 | 316 | 278 | 0.67 |  |
| Southwest Class Championships 2026 | 608 | 480 | 473 | 0.78 |  |
| Kings Island Open 2018 | 405 | 326 | 272 | 0.67 |  |
| Boston Chess Congress 2017 | 347 | 260 | 217 | 0.63 |  |
| Kings Island Open 2013 | 489 | 401 | 359 | 0.73 |  |
| Cleveland Open 2017 | 345 | 246 | 216 | 0.63 |  |
| Pacific Coast Open 2016 | 363 | 279 | 234 | 0.64 |  |
| Bradley Open 2018 | 305 | 212 | 177 | 0.58 |  |
| Golden State Open 2017 | 427 | 331 | 301 | 0.70 |  |
| Pacific Coast Open 2014 | 351 | 264 | 228 | 0.65 |  |
| Bradley Open 2016 | 267 | 176 | 149 | 0.56 |  |
| Golden State Open 2015 | 390 | 308 | 272 | 0.70 |  |
| Pacific Coast Open 2013 | 361 | 286 | 244 | 0.68 |  |
| Cleveland Open 2016 | 318 | 235 | 202 | 0.64 |  |
| Los Angeles Open 2017 | 339 | 267 | 224 | 0.66 |  |
| Los Angeles Open 2016 | 293 | 221 | 180 | 0.61 |  |
| Boston Chess Congress 2016 | 364 | 294 | 252 | 0.69 |  |
| Cleveland Open 2015 | 330 | 253 | 218 | 0.66 |  |
| Southern Open 2016 | 334 | 252 | 222 | 0.66 |  |
| Bradley Open 2019 | 288 | 212 | 178 | 0.62 |  |
| Eastern Chess Congress 2025 | 579 | 475 | 469 | 0.81 |  |
| Southern Open 2018 | 354 | 280 | 244 | 0.69 |  |
| Bradley Open 2015 | 283 | 203 | 174 | 0.61 |  |
| Cleveland Open 2014 | 339 | 260 | 230 | 0.68 |  |
| Southern Open 2017 | 339 | 270 | 230 | 0.68 |  |
| Southern Open 2019 | 300 | 225 | 191 | 0.64 |  |
| Continental Open 2014 | 353 | 287 | 245 | 0.69 |  |
| Continental Open 2016 | 395 | 265 | 288 | 0.73 |  |
| Los Angeles Open 2013 | 289 | 217 | 187 | 0.65 |  |
| George Washington Open 2017 | 315 | 244 | 214 | 0.68 |  |
| Boston Chess Congress 2014 | 276 | 215 | 179 | 0.65 | Under 1500 Section 2 |
| Golden State Open 2014 | 390 | 329 | 293 | 0.75 |  |
| Midwest Class Championships 2013 | 348 | 294 | 252 | 0.72 |  |
| Southern Open 2015 | 333 | 267 | 237 | 0.71 |  |
| Southern Open 2013 | 328 | 265 | 235 | 0.72 |  |
| World Open top 6 sections 1999 | 1589 | 1589 | 1496 | 0.94 | Under 2000 Section |
| DC Open 2025 | 401 | 319 | 315 | 0.79 |  |
| Continental Open 2013 | 272 | 218 | 188 | 0.69 |  |
| Boston Chess Congress 2015 | 315 | 269 | 233 | 0.74 |  |
| Southern Open 2014 | 264 | 206 | 182 | 0.69 |  |
| Cleveland Open 2013 | 312 | 267 | 231 | 0.74 |  |
| Los Angeles Open 2025 | 469 | 397 | 388 | 0.83 |  |
| Manhattan Open 2019 | 504 | 443 | 426 | 0.85 |  |
| Pacific Coast Open 2025 | 448 | 380 | 370 | 0.83 |  |
| Chicago Class 2025 | 366 | 303 | 289 | 0.79 |  |
| Continental Open 2025 | 340 | 273 | 265 | 0.78 |  |
| New York State Championship 2025 | 411 | 339 | 336 | 0.82 |  |
| Atlantic Open 2025 | 311 | 242 | 238 | 0.77 |  |
| Mid-America Open 2026 | 267 | 203 | 195 | 0.73 |  |
| Boston Chess Congress 2026 | 413 | 353 | 343 | 0.83 |  |
| Empire State Open 2021 | 293 | 231 | 224 | 0.76 |  |
| Midwest Class Championships 2025 | 362 | 306 | 293 | 0.81 |  |
| Washington Chess Congress 2023 | 309 | 250 | 243 | 0.79 |  |
| Bradley Open 2014 | 212 | 172 | 148 | 0.70 |  |
| Empire City Open 2019 | 379 | 323 | 317 | 0.84 |  |
| Atlantic City Open 2014 | 349 | 325 | 289 | 0.83 |  |
| Atlantic City Open 2024 | 513 | 472 | 456 | 0.89 |  |
| Cleveland Open 2025 | 250 | 194 | 193 | 0.77 |  |
| Indianapolis Open 2025 | 237 | 187 | 183 | 0.77 |  |
| Southern Class Championships 2026 | 250 | 206 | 196 | 0.78 |  |
| Bradley Open 2025 | 285 | 237 | 233 | 0.82 |  |
| Central New York Open 2023 | 189 | 142 | 139 | 0.74 |  |
| Southern Open 2025 | 237 | 192 | 187 | 0.79 |  |
| Boston Chess Congress 2013 | 227 | 227 | 179 | 0.79 |  |
| Central California Open 2025 | 220 | 176 | 172 | 0.78 |  |
| Golden State Open 2026 | 434 | 393 | 386 | 0.89 |  |
| DC Open 2010 | 585 | 585 | 542 | 0.93 |  |
| Eastern Class Championships 2025 | 232 | 194 | 189 | 0.81 |  |
| New York State High School Championship 2026 | 236 | 193 | 193 | 0.82 |  |
| World Open top 6 sections 2000 | 1240 | 1240 | 1197 | 0.97 |  |
| Continental Open 2011 | 270 | 270 | 228 | 0.84 |  |
| Continental Open 2012 | 263 | 263 | 221 | 0.84 |  |
| DC Open 2013 | 571 | 571 | 529 | 0.93 |  |
| Kings Island Open 2012 | 386 | 386 | 344 | 0.89 |  |
| Midwest Class Championships 2011 | 292 | 292 | 250 | 0.86 |  |
| Midwest Class Championships 2012 | 275 | 275 | 233 | 0.85 |  |
| Pacific Coast Open 2011 | 238 | 238 | 196 | 0.82 |  |
| Pacific Coast Open 2012 | 245 | 245 | 203 | 0.83 |  |
| Stamford Open 2019 | 221 | 187 | 182 | 0.82 |  |
| Continental Class 2023 | 230 | 199 | 192 | 0.83 |  |
| Cleveland Open 2011 | 238 | 238 | 202 | 0.85 |  |
| Cleveland Open 2012 | 259 | 259 | 223 | 0.86 |  |
| DC Open 2011 | 513 | 513 | 477 | 0.93 |  |
| Golden State Open 2011 | 283 | 283 | 247 | 0.87 |  |
| Golden State Open 2013 | 328 | 328 | 292 | 0.89 |  |
| Los Angeles Open 2011 | 198 | 198 | 162 | 0.82 |  |
| Los Angeles Open 2012 | 225 | 225 | 189 | 0.84 |  |
| Kings Island Open 2025 | 382 | 357 | 347 | 0.91 |  |
| Pittsburgh Open 2025 | 185 | 153 | 150 | 0.81 |  |
| Hartford Open 2025 | 211 | 181 | 177 | 0.84 |  |
| Boardwalk Open 2015 | 151 | 124 | 121 | 0.80 |  |
| Bradley Open 2012 | 228 | 228 | 198 | 0.87 |  |
| Bradley Open 2013 | 182 | 182 | 152 | 0.84 |  |
| Southern Open 2012 | 257 | 257 | 227 | 0.88 |  |
| Midwest Chess Congress 2022 | 107 | 84 | 82 | 0.77 |  |
| New York State Scholastic Championships Grades K-8 2026 | 1703 | 1680 | 1678 | 0.99 |  |
| Niagara Falls Open 2025 | 141 | 119 | 117 | 0.83 |  |
| Western Class Championships 2026 | 330 | 313 | 308 | 0.93 |  |
| George Washington Open 2026 | 217 | 203 | 198 | 0.91 |  |
| New York State Open 2025 | 99 | 85 | 82 | 0.83 |  |
| New York State Senior Championship With Young Adult Mi 2026 | 64 | 60 | 60 | 0.94 |  |
| DC International 2025 | 122 | 122 | 121 | 0.99 |  |

### Against rows in fbd5b02 since deleted

45 paired, 9 equal, 11 within 2%, 0 with no rebuilt row.

| Edition | Old total | Old without side events | New total | New / old | Not in cca-site |
|---|---:|---:|---:|---:|---|
| World Open top 6 sections 2023 | 2267 | 1835 | 1302 | 0.57 | Under 1200, Under 1000, Senior Amateur, Women's Championship, Under 13 Championship Open, Under 13 Championship Under 70, Under 13 Championship Under 14, Amateur Under 2200, Amateur Under 1800, Junior Open, Junior Under 1700, Junior Under 1100 |
| World Open top 6 sections 2025 | 1913 | 1520 | 1141 | 0.60 | Under 1200, Under 1000, Senior Amateur, Women's Championship, Under 13 Championship Open, Under 13 Championship Under 70, Under 13 Championship Under 14, Amateur Under 2200, Amateur Under 1800 |
| World Open top 6 sections 2024 | 1943 | 1616 | 1173 | 0.60 | Under 1200, Under 1000, Senior Amateur, Women's Championship, Under 13 Championship Open, Under 13 Championship Under 70, Under 13 Championship Under 14, Amateur Under 2200, Amateur Under 1800, Junior Open, Junior Under 1700, Junior Under 1100 |
| World Open top 6 sections 2017 | 1989 | 1541 | 1234 | 0.62 | Under 13 Championship Open, Under 13 Championship Under 14, Under 13 Championship Under 10, Under 13 Championship Under 60, Warmup, Women's Championship Open, Women's Championship Under 150, Senior Championship Open, Senior Championship Under 1810 |
| World Open top 6 sections 2022 | 2239 | 1830 | 1495 | 0.67 | Senior Amateur, Women's Championship, Under 13 Championship Open, Under 13 Championship Under 70, FIDE Under 2200, Under 13 Championship Under 14, Amateur Under 2200, Amateur Under 1800, Amateur Under 1400, FIDE Under 2400 |
| World Open top 6 sections 2018 | 1920 | 1527 | 1268 | 0.66 | Women's Championship, Under 13 Championship Open, Under 13 Championship Under 14, Under 13 Championship Under 10, Under 13 Championship Under 60, Warmup, Senior Amateur Under 2210, Senior Amateur Under 1810 |
| World Open top 6 sections 2019 | 2080 | 1678 | 1437 | 0.69 | Warmup, Senior Amateur Under 2210, Senior Amateur Under 1810, Women's Championship, Under 13 Championship Open, Under 13 Championship Under 14, Under 13 Championship Under 10, Under 13 Championship Under 60 |
| World Open top 6 sections 2015 | 1623 | 1513 | 1016 | 0.63 | 10-Minute Championship Open, 10-Minute Championship Under 1, 7-Minute Championship, Women's Championship, Warmup, Under 13 Championship Open, Under 13 Championship Under 14, Under 13 Championship Under 10, Under 13 Championship Under 60, Senior Amateur Under 2210, Senior Amateur Under 1810 |
| World Open top 6 sections 2014 | 1810 | 1581 | 1206 | 0.67 | 10-Minute Championship Open, 10-Minute Championship Under 1, 7-Minute Championship, Warmup, Under 13 Championship Open, Under 13 Championship Under 14, Under 13 Championship Under 10, Under 13 Championship Under 60, Senior Amateur Under 2210, Senior Amateur Under 1810, Women's Championship |
| World Open top 6 sections 2021 | 1649 | 1293 | 1100 | 0.67 | Warmup, Senior Amateur, Women's Championship, Under 13 Championship Open, Under 13 Championship Under 15, Under 13 Championship Under 11, Under 13 Championship Under 70 |
| World Open top 6 sections 2016 | 1826 | 1543 | 1281 | 0.70 | Under 13 Championship Open, Under 13 Championship Under 14, Under 13 Championship Under 10, Under 13 Championship Under 60, Senior Championship, Women's Championship, 10-Minute Championship Open, 10-Minute Championship Under 1 |
| Liberty Bell Open 2022 | 677 | 597 | 343 | 0.51 | 2-Day Under 2100 Section, 2-Day Under 1900 Section, 3-Day Major, 3-Day Under 2100 Section, 3-Day Under 1900 Section, 3-Day Under 1700 Section, 3-Day Under 1500 Section, 3-Day Under 1200 Section, 2-Day Under 1700 Section, 2-Day Under 1500 Section, 2-Day Under 1200 Section |
| Chicago Open 2022 | 1220 | 1220 | 998 | 0.82 | Under 2300 2 day, Under 2100 2 day, Under 1900 2 day, Under 1700 2 day, Under 1500 2 day, Under 1300 2 day, Under 1000 2 day |
| Liberty Bell Open 2026 | 687 | 566 | 546 | 0.79 |  |
| Liberty Bell Open 2025 | 642 | 524 | 514 | 0.80 |  |
| Liberty Bell Open 2023 | 579 | 488 | 464 | 0.80 |  |
| Liberty Bell Open 2024 | 570 | 470 | 456 | 0.80 |  |
| Chicago Open 2024 | 937 | 858 | 838 | 0.89 |  |
| Chicago Open 2023 | 1039 | 962 | 941 | 0.91 |  |
| Chicago Open 2025 | 968 | 902 | 876 | 0.90 |  |
| National Chess Congress 2014 | 731 | 605 | 650 | 0.89 |  |
| National Chess Congress 2015 | 675 | 590 | 603 | 0.89 |  |
| National Chess Congress 2016 | 589 | 589 | 635 | 1.08 |  |
| National Chess Congress 2017 | 643 | 643 | 682 | 1.06 |  |
| Chicago Open 2014 | 794 | 764 | 764 | 0.96 |  |
| National Chess Congress 2024 | 629 | 629 | 600 | 0.95 |  |
| National Chess Congress 2025 | 715 | 715 | 689 | 0.96 |  |
| Liberty Bell Open 2017 | 372 | 372 | 348 | 0.94 |  |
| National Chess Congress 2018 | 548 | 548 | 524 | 0.96 |  |
| Liberty Bell Open 2016 | 361 | 361 | 343 | 0.95 |  |
| National Chess Congress 2019 | 582 | 582 | 564 | 0.97 |  |
| Liberty Bell Open 2018 | 360 | 360 | 343 | 0.95 |  |
| Liberty Bell Open 2019 | 290 | 290 | 277 | 0.96 |  |
| Liberty Bell Open 2020 | 375 | 375 | 363 | 0.97 |  |
| National Chess Congress 2022 | 606 | 606 | 594 | 0.98 |  |
| National Chess Congress 2023 | 643 | 643 | 636 | 0.99 |  |
| Chicago Open 2015 | 890 | 890 | 890 | 1.00 |  |
| Chicago Open 2016 | 932 | 932 | 932 | 1.00 |  |
| Chicago Open 2017 | 988 | 988 | 988 | 1.00 |  |
| Chicago Open 2018 | 900 | 900 | 900 | 1.00 |  |
| Chicago Open 2019 | 914 | 914 | 914 | 1.00 |  |
| Chicago Open 2021 | 572 | 572 | 572 | 1.00 |  |
| Liberty Bell Open 2014 | 427 | 427 | 427 | 1.00 |  |
| Liberty Bell Open 2015 | 380 | 380 | 380 | 1.00 |  |
| National Chess Congress 2021 | 626 | 626 | 626 | 1.00 |  |
