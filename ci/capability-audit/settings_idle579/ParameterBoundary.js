// Actual public method calls with invalid JavaScript values. No result is
// manufactured here; the typed Service logs every raw resolution/rejection.
export async function parameterBoundary(context, report) {
  const cases = [
    ['missing', () => context.terminateSelfIfStartId()],
    ['extra', () => context.terminateSelfIfStartId(1, 2)],
    ['string', () => context.terminateSelfIfStartId('1')],
    ['null', () => context.terminateSelfIfStartId(null)],
    ['undefined', () => context.terminateSelfIfStartId(undefined)],
    ['zero', () => context.terminateSelfIfStartId(0)],
    ['negative', () => context.terminateSelfIfStartId(-1)],
    ['fractional', () => context.terminateSelfIfStartId(1.5)],
    ['nan', () => context.terminateSelfIfStartId(NaN)],
    ['infinity', () => context.terminateSelfIfStartId(Infinity)],
    ['overflow', () => context.terminateSelfIfStartId(2147483648)]
  ];
  for (const [label, invoke] of cases) {
    report('parameter.call', label, 0, 'null');
    try { report('parameter.return', label, 0, JSON.stringify(await invoke())); }
    catch (error) { report('parameter.error', label, typeof error.code === 'number' ? error.code : -1,
      JSON.stringify({ name: error.name, message: error.message })); }
  }
}
