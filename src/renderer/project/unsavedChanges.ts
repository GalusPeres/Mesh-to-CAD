import { useStore } from 'zustand';
import { createStore } from 'zustand/vanilla';

export type UnsavedChoice = 'save' | 'discard' | 'cancel';

/** A pending "save changes?" question, answered by the dialog in `ProjectLifecycle`. */
export interface UnsavedQuestion {
  name: string;
  answer(choice: UnsavedChoice): void;
}

const questionStore = createStore<{ question: UnsavedQuestion | null }>(() => ({
  question: null,
}));

export function useUnsavedQuestion(): UnsavedQuestion | null {
  return useStore(questionStore, (state) => state.question);
}

/** Ask whether to save the changes to `name`; a second question cancels the first. */
export function askToSave(name: string): Promise<UnsavedChoice> {
  questionStore.getState().question?.answer('cancel');
  return new Promise((resolve) => {
    questionStore.setState({
      question: {
        name,
        answer: (choice) => {
          questionStore.setState({ question: null });
          resolve(choice);
        },
      },
    });
  });
}
