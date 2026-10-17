// Restrict worker discovery only inside the root-owned serial SDK compiler.
const os = require('os');
const original = os.cpus.bind(os);
os.cpus = () => original().slice(0, 2);
if (typeof os.availableParallelism === 'function') os.availableParallelism = () => 2;
