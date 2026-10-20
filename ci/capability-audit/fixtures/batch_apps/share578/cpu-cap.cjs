// Bound worker discovery in the explicitly owned SDK build process only.
const os = require('os');
const actualCpus = os.cpus.bind(os);
os.cpus = () => actualCpus().slice(0, 2);
if (typeof os.availableParallelism === 'function') os.availableParallelism = () => 2;
