export interface CommonTranslations {
  buttons: {
    save: string;
    cancel: string;
    upload: string;
    download: string;
    reset: string;
    undo: string;
    redo: string;
    runInpainting: string;
    accept: string;
    confirm: string;
  };
  navigation: {
    fileManager: string;
    settings: string;
    shortcuts: string;
    uploadImage: string;
    uploadMask: string;
    rerunLastMask: string;
  };
  tooltips: {
    uploadImage: string;
    uploadMask: string;
    resetZoom: string;
    showOriginal: string;
    saveImage: string;
    zoomIn: string;
    zoomOut: string;
  };
  messages: {
    clickOrDrag: string;
    processing: string;
    loading: string;
    noMaskToReuse: string;
  };
}

export interface EditorTranslations {
  tools: {
    brush: string;
    eraser: string;
    zoom: string;
    pan: string;
    resetZoomPan: string;
    showOriginal: string;
    download: string;
    interactiveSeg: string;
  };
  messages: {
    drawMask: string;
    processingImage: string;
    generatingMask: string;
    clickToSeg: string;
    aiModelLoading: string;
  };
  sidebar: {
    brushSize: string;
    manualMode: string;
    paintByExample: string;
    clickToAddPoint: string;
    clickToRemoveArea: string;
  };
}

export interface SettingsTranslations {
  title: string;
  tabs: {
    model: string;
    general: string;
    advanced: string;
  };
  model: {
    selectModel: string;
    device: string;
    enableControlNet: string;
    controlNetMethod: string;
    switchModel: string;
    downloadingModel: string;
  };
  general: {
    theme: string;
    themeOptions: {
      light: string;
      dark: string;
      system: string;
    };
    language: string;
    enableFileManager: string;
    inputDirectory: string;
    outputDirectory: string;
  };
  advanced: {
    enableAutoSaving: string;
    enableDownloadMask: string;
    enableManualInpainting: string;
    enableUploadMask: string;
    quality: string;
  };
  parameters: {
    steps: string;
    guidanceScale: string;
    strength: string;
    sampler: string;
    seed: string;
    maskBlur: string;
    matchHistograms: string;
  };
}

export interface ErrorTranslations {
  fileUpload: {
    sizeTooLarge: string;
    invalidFormat: string;
    uploadFailed: string;
    multipleFiles: string;
    noFileSelected: string;
  };
  processing: {
    failed: string;
    timeout: string;
    modelLoadFailed: string;
    outOfMemory: string;
  };
  network: {
    connectionFailed: string;
    serverError: string;
    requestTimeout: string;
  };
  validation: {
    invalidInput: string;
    maskRequired: string;
    imageRequired: string;
  };
}

export interface ShortcutsTranslations {
  title: string;
  general: {
    title: string;
    undo: string;
    redo: string;
    acceptInpainting: string;
    cancelInpainting: string;
    save: string;
  };
  editor: {
    title: string;
    pan: string;
    decreaseBrushSize: string;
    increaseBrushSize: string;
    toggleOriginal: string;
    resetZoom: string;
  };
  view: {
    title: string;
    toggleSettings: string;
    toggleShortcuts: string;
    toggleTheme: string;
  };
  drawing: {
    title: string;
    freeDrawing: string;
    multiStrokeDrawing: string;
    rectangleDrawing: string;
  };
}

export interface TranslationResource {
  common: CommonTranslations;
  editor: EditorTranslations;
  settings: SettingsTranslations;
  errors: ErrorTranslations;
  shortcuts: ShortcutsTranslations;
}

export type TranslationNamespace = keyof TranslationResource;