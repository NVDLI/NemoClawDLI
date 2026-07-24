// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import test from 'node:test';
import { sharedRuntime, canvasRuntime } from './course_runtime_fixture.mjs';

const { HELPER_FNS } = sharedRuntime;
const { HELPER_CATEGORIES, helperMenuOrphans } = canvasRuntime;

test('every exposed course helper has a reviewed menu category', () => {
  assert.deepEqual(helperMenuOrphans(), []);
});

test('an unclassified helper mutation is rejected without a maintained count', () => {
  const helperFns = { ...HELPER_FNS, newlyIntroducedHelper() {} };
  assert.deepEqual(helperMenuOrphans({ helperFns }), ['newlyIntroducedHelper']);
});

test('removing a helper from its category is rejected', () => {
  const categories = HELPER_CATEGORIES.map(([heading, helpers]) => [
    heading,
    helpers.filter(name => name !== 'chat'),
  ]);
  assert.deepEqual(helperMenuOrphans({ categories }), ['chat']);
});
