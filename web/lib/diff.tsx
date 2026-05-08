import React from "react";

type Token = {
  value: string;
  changed: boolean;
};

export function highlightedDiff(before: string | null, after: string | null, side: "before" | "after") {
  const beforeTokens = tokenize(before || "");
  const afterTokens = tokenize(after || "");
  const matchedBefore = new Set<number>();
  const matchedAfter = new Set<number>();
  const afterBuckets = new Map<string, number[]>();

  afterTokens.forEach((token, index) => {
    if (!isWord(token)) {
      return;
    }
    const key = normalizeToken(token);
    afterBuckets.set(key, [...(afterBuckets.get(key) || []), index]);
  });

  beforeTokens.forEach((token, beforeIndex) => {
    if (!isWord(token)) {
      return;
    }
    const key = normalizeToken(token);
    const bucket = afterBuckets.get(key);
    const afterIndex = bucket?.find((index) => !matchedAfter.has(index));
    if (afterIndex !== undefined) {
      matchedBefore.add(beforeIndex);
      matchedAfter.add(afterIndex);
    }
  });

  const tokens: Token[] =
    side === "before"
      ? beforeTokens.map((value, index) => ({
          value,
          changed: isWord(value) && !matchedBefore.has(index)
        }))
      : afterTokens.map((value, index) => ({
          value,
          changed: isWord(value) && !matchedAfter.has(index)
        }));

  return tokens.map((token, index) =>
    token.changed ? (
      <mark className="changedWord" key={`${side}-${index}`}>
        {token.value}
      </mark>
    ) : (
      <React.Fragment key={`${side}-${index}`}>{token.value}</React.Fragment>
    )
  );
}

export function hammingDistance(left: string, right: string) {
  let value: bigint;
  try {
    value = BigInt(`0x${left}`) ^ BigInt(`0x${right}`);
  } catch {
    return 64;
  }

  let distance = 0;
  while (value > 0n) {
    distance += Number(value & 1n);
    value >>= 1n;
  }
  return distance;
}

export function changedImageIndexes(beforeHashes: string[], afterHashes: string[], threshold = 8) {
  const matchedBefore = new Set<number>();
  const matchedAfter = new Set<number>();

  beforeHashes.forEach((beforeHash, beforeIndex) => {
    const matchIndex = afterHashes.findIndex(
      (afterHash, afterIndex) => !matchedAfter.has(afterIndex) && hammingDistance(beforeHash, afterHash) <= threshold
    );
    if (matchIndex >= 0) {
      matchedBefore.add(beforeIndex);
      matchedAfter.add(matchIndex);
    }
  });

  return {
    before: beforeHashes.map((_, index) => index).filter((index) => !matchedBefore.has(index)),
    after: afterHashes.map((_, index) => index).filter((index) => !matchedAfter.has(index))
  };
}

function tokenize(value: string) {
  return value.match(/[\p{L}\p{N}_]+|[^\p{L}\p{N}_]+/gu) || [];
}

function isWord(value: string) {
  return /[\p{L}\p{N}_]/u.test(value);
}

function normalizeToken(value: string) {
  return value.toLowerCase().replace(/[^\p{L}\p{N}_]/gu, "");
}
