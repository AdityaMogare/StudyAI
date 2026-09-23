"""CS 101 exam-prep content: explanations, follow-ups, and quiz items.

Used when Bedrock chat is unavailable (LOCAL_MODE). Keys match syllabus topic names.
"""

from __future__ import annotations

from typing import Any

CURRICULUM: dict[str, dict[str, Any]] = {
    "Programming Fundamentals": {
        "explanation": (
            "Programs store values in **variables** with types (int, string, bool). "
            "**Control flow** (`if`, loops) decides what runs. **Functions** package a "
            "step so you can reuse it. Trace one input through the program on paper "
            "before you worry about syntax."
        ),
        "followups": [
            "Write a function that returns the larger of two numbers without using `max`.",
            "What is the difference between an assignment (`x = 3`) and a comparison (`x == 3`)?",
        ],
        "quiz": [
            {"q": "What does a function return if you omit a return statement (in typical CS 101 languages)?", "hint": "A default empty/None/undefined value."},
            {"q": "Name two loop types and when you would pick each.", "hint": "for = known count; while = unknown until a condition."},
            {"q": "Why do we use functions instead of copy-pasting the same code?", "hint": "Reuse, testing, one place to fix bugs."},
            {"q": "What is a boolean expression used for?", "hint": "Decisions in if/while."},
            {"q": "Give an example of a type error.", "hint": "Adding a string to an int without conversion."},
        ],
    },
    "Arrays and Linked Lists": {
        "explanation": (
            "An **array** (or list) stores items in a contiguous block: index `i` is O(1), "
            "but inserting at the front is O(n) because later items shift. A **linked list** "
            "stores nodes with pointers: insert/delete at a known node is O(1), but finding "
            "the k-th item is O(n). Pick arrays for random access; lists for lots of inserts "
            "in the middle."
        ),
        "followups": [
            "Why is `arr[i]` fast but `list.get(i)` on a singly linked list slow?",
            "How would you reverse a singly linked list in one pass?",
        ],
        "quiz": [
            {"q": "Time complexity of accessing index i in an array vs a singly linked list?", "hint": "O(1) vs O(n)."},
            {"q": "When is inserting at the head of a linked list O(1)?", "hint": "When you already have the head pointer."},
            {"q": "Why can arrays waste or run out of space?", "hint": "Fixed or doubling capacity vs scattered nodes."},
            {"q": "What extra memory does each linked-list node store?", "hint": "Pointer(s) to neighbor(s)."},
            {"q": "How do you detect a cycle in a linked list?", "hint": "Floyd’s tortoise and hare."},
        ],
    },
    "Stacks and Queues": {
        "explanation": (
            "A **stack** is LIFO (last in, first out): push/pop at the same end. Use it for "
            "undo, call stacks, and matching brackets. A **queue** is FIFO (first in, first out): "
            "enqueue at the back, dequeue at the front. Use it for BFS and fair scheduling. "
            "The difference is *which end* leaves first, not the items themselves."
        ),
        "followups": [
            "Which structure would you use to check that parentheses in an expression are balanced?",
            "Simulate BFS with a queue on a tiny 4-node graph.",
        ],
        "quiz": [
            {"q": "After push(1), push(2), pop(), what does a stack return?", "hint": "2 (LIFO)."},
            {"q": "After enqueue(1), enqueue(2), dequeue(), what does a queue return?", "hint": "1 (FIFO)."},
            {"q": "Why does a function call need a stack?", "hint": "Return addresses and locals nest."},
            {"q": "Name one real system that behaves like a queue.", "hint": "Printer jobs, request handlers."},
            {"q": "Can you implement a queue with two stacks? Sketch the idea.", "hint": "Inbound stack + reverse onto outbound."},
        ],
    },
    "Hash Tables": {
        "explanation": (
            "A **hash table** maps a key to a bucket with a hash function so average lookup, "
            "insert, and delete are O(1). Two keys can **collide** (same bucket). We resolve "
            "collisions with chaining (a list per bucket) or open addressing (probe for the "
            "next slot). Load factor ≈ items/buckets; when it gets high, resize and rehash."
        ),
        "followups": [
            "If two names hash to the same bucket, what does chaining store there?",
            "Why can a bad hash function make a hash table as slow as a linked list?",
        ],
        "quiz": [
            {"q": "Average vs worst-case lookup in a hash table?", "hint": "O(1) vs O(n) if everything collides."},
            {"q": "What is a collision?", "hint": "Two keys map to the same bucket."},
            {"q": "Name two collision strategies.", "hint": "Chaining and open addressing / probing."},
            {"q": "What is load factor and why resize?", "hint": "n/buckets; high load → more collisions."},
            {"q": "Why must keys be immutable (or have a stable hash)?", "hint": "If the hash changes, you cannot find the item."},
        ],
    },
    "Trees and Binary Search Trees": {
        "explanation": (
            "A **tree** is a hierarchy of nodes with one parent (except the root). In a "
            "**BST**, left subtree < node < right subtree, so search/insert/delete are "
            "O(h). If the tree is balanced, h ≈ log n; if it is a stick, h = n. Traversals: "
            "inorder (sorted for BSTs), preorder, postorder."
        ),
        "followups": [
            "Draw the BST after inserting 5, 3, 7, 4. What is an inorder walk?",
            "Why can BST search be O(n)? How do balanced trees fix that?",
        ],
        "quiz": [
            {"q": "What BST property lets you skip half the tree (when balanced)?", "hint": "Left < node < right."},
            {"q": "Inorder traversal of a BST produces what order?", "hint": "Sorted keys."},
            {"q": "Height of a complete binary tree with n nodes?", "hint": "≈ log₂ n."},
            {"q": "What is the difference between a binary tree and a BST?", "hint": "BST adds an ordering invariant."},
            {"q": "Where is the minimum key in a BST?", "hint": "Leftmost node."},
        ],
    },
    "Searching Algorithms": {
        "explanation": (
            "**Linear search** checks items one by one: O(n), works on unsorted data. "
            "**Binary search** needs a sorted array: compare the middle, then throw away "
            "half. Each step halves the search space, so time is O(log n). If the array "
            "is unsorted, sort first (extra cost) or use linear/hashing instead."
        ),
        "followups": [
            "On a sorted array of 16 items, about how many comparisons does binary search need in the worst case?",
            "Why is binary search invalid on a linked list even if values look sorted?",
        ],
        "quiz": [
            {"q": "Precondition for binary search?", "hint": "Random-access sorted sequence."},
            {"q": "Worst-case of binary search?", "hint": "O(log n)."},
            {"q": "When is linear search better than binary search?", "hint": "Tiny n, or data not sorted / not an array."},
            {"q": "What does ‘throw away half’ mean in one comparison?", "hint": "If target < mid, ignore the right half."},
            {"q": "Is binary search O(log n) on a BST? On a linked list?", "hint": "Balanced BST yes; list no (no O(1) mid)."},
        ],
    },
    "Sorting Algorithms": {
        "explanation": (
            "**Selection/insertion** sort are simple O(n²). **Merge sort** splits, sorts halves, "
            "merges: always O(n log n), needs extra memory. **Quick sort** partitions around a "
            "pivot: average O(n log n), worst O(n²) if pivots are terrible. Know best/worst "
            "and whether the sort is stable (equal keys keep order)."
        ),
        "followups": [
            "Walk through one merge step on [1,4,5] and [2,3,6].",
            "When does quicksort degrade to O(n²), and how do we reduce that risk?",
        ],
        "quiz": [
            {"q": "Merge sort time and extra space?", "hint": "O(n log n) time, O(n) extra."},
            {"q": "Quicksort average vs worst case?", "hint": "O(n log n) vs O(n²)."},
            {"q": "Which of insertion vs merge is typically stable?", "hint": "Both can be; insertion and merge usually taught as stable."},
            {"q": "Why is insertion sort fast on nearly sorted arrays?", "hint": "Each insert moves very little → ~O(n)."},
            {"q": "What does the merge step assume about its two inputs?", "hint": "Each half is already sorted."},
        ],
    },
    "Big-O Analysis": {
        "explanation": (
            "**Big-O** describes how time/space grow as n grows, ignoring constants. "
            "O(1) constant, O(log n) halving, O(n) one pass, O(n log n) typical good sorts, "
            "O(n²) nested loops over n. Drop lower-order terms: 3n²+2n is O(n²). Count "
            "the dominant loop structure, not every +1."
        ),
        "followups": [
            "A loop i=1..n with an inner loop j=1..i: what is the Big-O?",
            "Why is binary search O(log n) and not O(n/2)?",
        ],
        "quiz": [
            {"q": "Is O(2n) different from O(n)?", "hint": "No — constants are dropped."},
            {"q": "Nested loop i=1..n, j=1..n is what class?", "hint": "O(n²)."},
            {"q": "What does O(1) extra space mean?", "hint": "Memory does not grow with n."},
            {"q": "Best / average / worst — which does interview Big-O usually quote?", "hint": "Worst case unless asked otherwise."},
            {"q": "log₂(1_000_000) is about what?", "hint": "≈ 20."},
        ],
    },
    "Recursion": {
        "explanation": (
            "A **recursive** function solves a smaller copy of the same problem. You need "
            "(1) a **base case** that stops, and (2) a recursive case that moves toward it. "
            "Each call sits on the **call stack**. Missing a base case → infinite recursion. "
            "Tree recursion (Fibonacci) can be exponential unless you memoize."
        ),
        "followups": [
            "Write factorial with a clear base case. What happens if the base case is wrong?",
            "Why is naive recursive Fibonacci so slow? What is one fix?",
        ],
        "quiz": [
            {"q": "What are the two parts of a correct recursive function?", "hint": "Base case + recursive case that shrinks."},
            {"q": "What data structure implements recursion in the machine?", "hint": "The call stack."},
            {"q": "Stack overflow usually means what bug?", "hint": "No/unreachable base case, or too-deep recursion."},
            {"q": "Convert a simple tail recursion to a loop in one sentence.", "hint": "Keep the same variables and iterate."},
            {"q": "When is recursion the natural fit?", "hint": "Trees, divide-and-conquer, nested structure."},
        ],
    },
    "Object-Oriented Programming": {
        "explanation": (
            "**OOP** models data + behavior as **objects**. A **class** is the blueprint. "
            "**Encapsulation** hides internals. **Inheritance** reuses a parent’s interface. "
            "**Polymorphism** lets different classes respond to the same method name "
            "(e.g. `shape.area()`). Prefer a clear noun (Student, HashTable) over a bag of functions."
        ),
        "followups": [
            "Give a polymorphism example with Animal.speak() for Dog and Cat.",
            "What should stay private in a BankAccount class, and why?",
        ],
        "quiz": [
            {"q": "Class vs object?", "hint": "Blueprint vs instance."},
            {"q": "What does encapsulation protect?", "hint": "Invariants / internal state."},
            {"q": "Inheritance vs composition — one-line distinction.", "hint": "is-a vs has-a."},
            {"q": "What is method overriding?", "hint": "Child replaces parent’s method."},
            {"q": "Why use an interface/abstract class?", "hint": "Share a contract without sharing implementation."},
        ],
    },
    "Complexity and Correctness": {
        "explanation": (
            "A program can be fast and **wrong**. **Correctness** means it meets the spec "
            "for every valid input. **Loop invariants** are facts that stay true each "
            "iteration and prove the result at the end. Test edge cases: empty, one item, "
            "already sorted, duplicates, negatives."
        ),
        "followups": [
            "State a loop invariant for scanning an array to find the maximum.",
            "List three edge cases for binary search.",
        ],
        "quiz": [
            {"q": "What is a loop invariant?", "hint": "A fact true before/after each iteration."},
            {"q": "Name three edge cases for a sort function.", "hint": "Empty, one element, duplicates."},
            {"q": "Does passing tests prove correctness?", "hint": "No — tests show presence of bugs, not absence."},
            {"q": "Off-by-one bugs usually live where?", "hint": "Loop bounds and mid = (lo+hi)/2."},
            {"q": "Why argue correctness separately from Big-O?", "hint": "Speed is useless if the answer is wrong."},
        ],
    },
    "Graphs BFS and DFS": {
        "explanation": (
            "A **graph** is nodes + edges. Store it as an adjacency list (usual) or matrix. "
            "**BFS** uses a queue: explores level by level — shortest path in unweighted graphs. "
            "**DFS** uses a stack/recursion: goes deep first — cycles, topological ideas, components. "
            "Mark visited nodes so you do not loop forever."
        ),
        "followups": [
            "On a 3-node line A-B-C, list BFS and DFS visit orders from A.",
            "Why does BFS find shortest paths when every edge has the same weight?",
        ],
        "quiz": [
            {"q": "BFS uses which structure? DFS?", "hint": "Queue vs stack/recursion."},
            {"q": "When is BFS the shortest-path algorithm?", "hint": "Unweighted (or equal-weight) edges."},
            {"q": "Adjacency list vs matrix space?", "hint": "O(n+m) vs O(n²)."},
            {"q": "Why mark nodes visited?", "hint": "Avoid infinite cycles."},
            {"q": "Connected component: BFS or DFS?", "hint": "Either — both explore a component."},
        ],
    },
    "System Design": {
        "explanation": (
            "In a **system design** interview, start with requirements (functional + scale), "
            "estimate QPS/storage, sketch API + data model, then pick storage, cache, and "
            "how you shard or replicate. Call out bottlenecks and what you would measure. "
            "Do not jump to Kubernetes before the data flow is clear."
        ),
        "followups": [
            "Design a URL shortener: API, data model, and how you handle 100M new links/day.",
            "Where would you put a cache in a read-heavy news feed, and what do you invalidate?",
        ],
        "quiz": [
            {"q": "Walk through designing a URL shortener. What is the data model and how do you generate short codes?", "hint": "hash or counter + base62; store long URL; cache hot keys."},
            {"q": "A read-heavy API is slow. Name two design moves before you rewrite the app.", "hint": "cache, CDN, read replicas, pagination."},
            {"q": "What numbers do you estimate first in a system design interview?", "hint": "QPS, payload size, storage, latency SLO."},
            {"q": "SQL vs NoSQL — when do you pick each for a new service?", "hint": "SQL for relations/transactions; NoSQL for huge simple key lookup or flexible docs."},
            {"q": "How do you keep a session store highly available?", "hint": "replication, sticky sessions vs shared Redis, failover."},
        ],
    },
}


def curriculum_for(topic_name: str | None) -> dict[str, Any] | None:
    if not topic_name:
        return None
    if topic_name in CURRICULUM:
        return CURRICULUM[topic_name]
    lower = topic_name.lower()
    for name, payload in CURRICULUM.items():
        if lower in name.lower() or name.lower() in lower:
            return payload
    return None


def match_topic_name(query: str, topic_names: list[str]) -> str | None:
    q = (query or "").strip().lower()
    if not q:
        return None
    for name in topic_names:
        if q == name.lower() or q in name.lower() or name.lower() in q:
            return name
    from shared.local_store import lexical_distance

    best: tuple[float, str] | None = None
    for name in topic_names:
        dist = lexical_distance(query, name)
        if best is None or dist < best[0]:
            best = (dist, name)
    if best and best[0] <= 0.75:
        return best[1]
    return None
