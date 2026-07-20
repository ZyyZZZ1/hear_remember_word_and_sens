import random
from collections import Counter

random.seed(42)
voices = ['davefx', 'sharvard', 'claude', 'daniela']
results = [random.choice(voices) for _ in range(1000)]
c = Counter(results)
for k in sorted(c):
    print(k, c[k])