import { useTranslation } from 'react-i18next';
import { TranslationNamespace, TranslationResource } from '../i18n/types';

export function useTypedTranslation<Namespace extends TranslationNamespace>(
  namespace: Namespace
) {
  const { t, i18n } = useTranslation(namespace);

  const typedT = (key: string, options?: any) => {
    return t(key, options);
  };

  return {
    t: typedT,
    i18n,
  };
}