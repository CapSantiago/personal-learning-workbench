// Offline Windows OCR adapter. Built with the installed .NET Framework compiler.
using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Web.Script.Serialization;
using Windows.Foundation;
using Windows.Media.Ocr;
using Windows.Storage;
using Windows.Graphics.Imaging;

class PlwOcrHelper {
    static readonly JavaScriptSerializer Json = new JavaScriptSerializer();

    static T Wait<T>(IAsyncOperation<T> operation) {
        var info = (IAsyncInfo)operation;
        var deadline = DateTime.UtcNow.AddSeconds(30);
        try {
            while (info.Status == AsyncStatus.Started) {
                if (DateTime.UtcNow > deadline) {
                    info.Cancel();
                    throw new TimeoutException("图片识别超过 30 秒，请降低图片分辨率后重试。");
                }
                Thread.Sleep(20);
            }
            if (info.Status != AsyncStatus.Completed)
                throw info.ErrorCode ?? new Exception("Windows OCR 未完成。");
            return operation.GetResults();
        } finally { info.Close(); }
    }

    static int Main(string[] args) {
        Console.OutputEncoding = new System.Text.UTF8Encoding(false);
        try {
            var languages = OcrEngine.AvailableRecognizerLanguages;
            if (args.Length == 1 && args[0] == "--capabilities") {
                Console.WriteLine(Json.Serialize(new {
                    languages = languages.Select(item => item.LanguageTag).ToArray(),
                    max_image_dimension = OcrEngine.MaxImageDimension
                }));
                return 0;
            }
            if (args.Length != 1) throw new ArgumentException("需要一份图片。");
            var input = new FileInfo(args[0]);
            if (!input.Exists || input.Length > 64 * 1024 * 1024)
                throw new ArgumentException("图片不存在或超过识别大小限制。");
            var language = languages.FirstOrDefault(item => item.LanguageTag.StartsWith("zh-Hans"))
                        ?? languages.FirstOrDefault(item => item.LanguageTag.StartsWith("en"));
            if (language == null) throw new Exception("此电脑未提供中文或英文 OCR 语言。");
            var engine = OcrEngine.TryCreateFromLanguage(language);
            if (engine == null) throw new Exception("Windows OCR 引擎不可用。");
            var file = Wait(StorageFile.GetFileFromPathAsync(input.FullName));
            using (var stream = Wait(file.OpenAsync(FileAccessMode.Read))) {
                var decoder = Wait(BitmapDecoder.CreateAsync(stream));
                if (decoder.PixelWidth > 4000 || decoder.PixelHeight > 4000)
                    throw new ArgumentException("识别图片边长不能超过 4000 像素。");
                using (var bitmap = Wait(decoder.GetSoftwareBitmapAsync(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Premultiplied))) {
                    var result = Wait(engine.RecognizeAsync(bitmap));
                    Console.WriteLine(Json.Serialize(new {
                        text = String.Join("\n", result.Lines.Select(line => line.Text)),
                        language = language.LanguageTag,
                        engine = "Windows.Media.Ocr"
                    }));
                }
            }
            return 0;
        } catch (Exception error) {
            Console.Error.WriteLine(error.Message);
            return 1;
        }
    }
}
