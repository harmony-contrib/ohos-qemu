"""Correlate real process DMA-BUF inodes across the two-buffer allocation lifecycle."""
import re


def verify_samples(samples, pid, allocation_kib):
    if (type(pid) is not int or pid <= 1 or not isinstance(allocation_kib, list) or
            len(allocation_kib) != 2 or any(type(n) is not int or n < 16384 for n in allocation_kib)):
        raise ValueError('actual ordinary process and allocation geometry required')
    states = []
    sizes = {}
    baseline = None
    for text in samples:
        if not text.startswith('Dma-buf objects usage of processes:\n'):
            raise ValueError('real kernel DMA-BUF table required')
        current = set()
        for line in text.splitlines():
            match = re.match(r'^(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+', line)
            if match is None or int(match[2]) != pid:
                continue
            size, inode = int(match[4]), int(match[5])
            if size <= 0 or inode <= 0 or (inode in sizes and sizes[inode] != size):
                raise ValueError('real buffer size or inode changed across observations')
            sizes[inode] = size
            current.add(inode)  # Multiple FDs do not create additional allocations.
        if baseline is None:
            baseline = current.copy()
        if not baseline.issubset(current):
            raise ValueError('pre-existing application buffers changed during the accounting test')
        allocated = current - baseline
        if not states or states[-1] != allocated:
            states.append(allocated)
    if len(states) != 5 or [len(state) for state in states] != [0, 1, 2, 1, 0]:
        raise ValueError('kernel did not observe both allocations and both releases')
    first = next(iter(states[1]))
    second = next(iter(states[3]))
    if first == second or states[2] != {first, second} or set(sizes) - baseline != {first, second}:
        raise ValueError('kernel inode ownership does not match ordered release')
    if [sizes[first], sizes[second]] != [n * 1024 for n in allocation_kib]:
        raise ValueError('kernel buffer byte sizes differ from actual public allocation geometry')
    return dict(pid=pid, inodes=[first, second], bytes=[sizes[first], sizes[second]],
                baseline_inodes=sorted(baseline), observed_allocation_counts=[len(state) for state in states], closed=[])
