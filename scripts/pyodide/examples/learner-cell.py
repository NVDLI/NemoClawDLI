# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

questions = inputs.get("questions", [
    "Why does a worker keep the page responsive?",
    "What should Reset clear?",
])

result = {
    "question_count": len(questions),
    "longest_question": max(questions, key=len),
    "words_per_question": [len(question.split()) for question in questions],
}

# The last expression is displayed as the cell value. Prints remain visible as progress output.
result
