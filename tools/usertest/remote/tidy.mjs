// The fitted planes in the view. Tools that end at a plane need it shown; before the
// part is judged, the user clears the view: planes no feature has used are still drawn
// as large plates over the part (used ones are hidden by the app).

/** Whether the tree hides the feature's drawing (the eye, or used construction). */
async function hidden(d, featureId) {
  return ((await d.state()).hidden?.owners ?? []).includes(featureId);
}

/**
 * Show or hide the fitted planes with the eye in the tree, checking what the tree hides
 * first, since the eye toggles. Returns what could not be done.
 */
export async function showPlanes(ctx, show) {
  const { d, planes } = ctx;
  if (!planes) return [];
  const problems = [];
  for (const [name, plane] of Object.entries(planes)) {
    if ((await hidden(d, plane.id)) !== show) continue;
    await d.press(`tree-eye-${plane.id}`);
    if ((await hidden(d, plane.id)) === show) {
      problems.push(`the eye does not ${show ? 'show' : 'hide'} the ${name} plane`);
    }
  }
  return problems;
}
