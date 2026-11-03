import { preprocessing } from './preprocessing.js';
import { finalSelection } from './selection.js';
import { toneSummary, recommendations } from './tone_results.js';

export function result(state) {
  const data = state.result;
  return `${toneSummary(data)}
    ${preprocessing(data.preprocessamento)}
    ${recommendations(data)}
    ${finalSelection(data.preprocessamento)}`;
}
