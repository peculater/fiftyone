import { useEffect } from "react";
import { useRecoilValue, useSetRecoilState } from "recoil";
import * as fos from "@fiftyone/state";
import { usePanelStatePartial } from "@fiftyone/spaces";
import { fetchExtendedStage } from "./fetch";

export default function useExtendedStageEffect() {
  const datasetName = useRecoilValue(fos.datasetName);
  const view = useRecoilValue(fos.view);
  const [loadedPlot] = usePanelStatePartial("loadedPlot", null, true);
  const setOverrideStage = useSetRecoilState(
    fos.extendedSelectionOverrideStage
  );
  const extendedSelection = useRecoilValue(fos.extendedSelection);

  useEffect(() => {
    if (loadedPlot && Array.isArray(extendedSelection)) {
      fetchExtendedStage({
        datasetName,
        view,
        patchesField: loadedPlot.patches_field,
        selection: extendedSelection,
      }).then((res) => {
        setOverrideStage({
          [res._cls]: res.kwargs,
        });
      });
    }
  }, [datasetName, loadedPlot?.patches_field, view, extendedSelection]);
}
