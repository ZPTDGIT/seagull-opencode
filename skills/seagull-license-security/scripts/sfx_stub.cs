// Seagull 单文件自解压 SFX stub
// 布局: [stub.exe][marker 18B][payload.zip][int64 zip_len][magic TKPROEND]
// 编译: csc /nologo /target:exe /platform:x64 /optimize+ /out:stub.exe /win32icon:app.ico ^
//          /r:System.IO.Compression.FileSystem.dll /r:System.IO.Compression.dll sfx_stub.cs
// 组装: 见 assemble_delivery.py
//
// 要点:
//  - 不能用 PyInstaller onefile 尾部追加(其 bootloader cookie 必须在文件尾), 这才是正解
//  - 首跑解压到 %LOCALAPPDATA%\<APP_FOLDER>\app, stamp 文件防重复解压
//  - csc 源码里的中文一律 \uXXXX 转义, 彻底绕开源文件编码坑
//  - 解压后 shell 启动内部「破解启动器.exe」, stub 立即退出
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Text;

class Sfx
{
    // 重新打包 payload 后改这里, 强制重新解压
    const string BUILD = "BUILD-2026-10-03";
    const string MARK = "<<<APP-PKG-V1>>>";
    const string APP_FOLDER = "CrackedApp";                    // <- 换目标改名
    // \u7834\u89e3\u542f\u52a8\u5668.exe == 破解启动器.exe
    const string LAUNCHER = "\u7834\u89e3\u542f\u52a8\u5668.exe";

    static byte[] _end = Encoding.ASCII.GetBytes("TKPROEND");

    static bool Same(byte[] a, byte[] b)
    {
        if (a.Length != b.Length) return false;
        for (int i = 0; i < a.Length; i++) if (a[i] != b[i]) return false;
        return true;
    }

    static void CopyN(Stream src, Stream dst, long n)
    {
        byte[] buf = new byte[1024 * 1024];
        long left = n;
        while (left > 0)
        {
            int want = (int)Math.Min(buf.Length, left);
            int got = src.Read(buf, 0, want);
            if (got <= 0) throw new IOException("payload read error");
            dst.Write(buf, 0, got);
            left -= got;
        }
    }

    static int Fail(string msg)
    {
        Console.WriteLine("[-] " + msg);
        Console.WriteLine("    按任意键退出...");
        try { Console.ReadKey(true); } catch { }
        return 1;
    }

    [STAThread]
    static int Main(string[] args)
    {
        try { Console.Title = "Cracked App SFX"; } catch { }
        string self = Process.GetCurrentProcess().MainModule.FileName;
        long zipStart;
        long zipLen;
        using (var fs = File.OpenRead(self))
        {
            if (fs.Length < 1024) return Fail("\u6587\u4ef6\u4e0d\u5b8c\u6574");
            fs.Seek(-16, SeekOrigin.End);
            byte[] tail = new byte[16];
            if (fs.Read(tail, 0, 16) != 16) return Fail("\u8bfb\u53d6\u5c3e\u90e8\u5931\u8d25");
            byte[] magic = new byte[8];
            Array.Copy(tail, 8, magic, 0, 8);
            if (!Same(magic, _end)) return Fail("\u672a\u627e\u5230\u5185\u5d4c\u6570\u636e");
            zipLen = BitConverter.ToInt64(tail, 0);
            if (zipLen <= 0 || zipLen > fs.Length - 64) return Fail("\u5185\u5d4c\u6570\u636e\u957f\u5ea6\u5f02\u5e38");
            zipStart = fs.Length - 16 - zipLen;
            byte[] mb = Encoding.ASCII.GetBytes(MARK);
            if (zipStart >= mb.Length)
            {
                fs.Seek(zipStart - mb.Length, SeekOrigin.Begin);
                byte[] m = new byte[mb.Length];
                fs.Read(m, 0, m.Length);
                if (!Same(m, mb)) return Fail("\u5185\u5d4c\u6570\u636e\u6807\u8bb0\u5f02\u5e38");
            }
        }

        string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), APP_FOLDER);
        string appDir = Path.Combine(root, "app");
        string stampFile = Path.Combine(root, "stamp.txt");
        string launcher = Path.Combine(appDir, LAUNCHER);
        bool need = true;
        try
        {
            if (File.Exists(stampFile) && File.ReadAllText(stampFile).Trim() == BUILD && File.Exists(launcher))
                need = false;
        }
        catch { }

        if (need)
        {
            Console.WriteLine("[*] \u9996\u6b21\u8fd0\u884c\uff1a\u6b63\u5728\u89e3\u538b\u5230 " + appDir);
            if (Directory.Exists(appDir))
            {
                try { Directory.Delete(appDir, true); } catch { }
            }
            Directory.CreateDirectory(root);
            string tmpZip = Path.Combine(Path.GetTempPath(), "pkg_" + Guid.NewGuid().ToString("N") + ".zip");
            using (var src = File.OpenRead(self))
            using (var dst = File.Create(tmpZip))
            {
                src.Seek(zipStart, SeekOrigin.Begin);
                CopyN(src, dst, zipLen);
            }
            ZipFile.ExtractToDirectory(tmpZip, appDir);
            try { File.Delete(tmpZip); } catch { }
            File.WriteAllText(stampFile, BUILD);
            Console.WriteLine("[+] \u89e3\u538b\u5b8c\u6210");
        }

        if (!File.Exists(launcher)) return Fail("\u542f\u52a8\u5668\u7f3a\u5931: " + launcher);
        var psi = new ProcessStartInfo(launcher);
        psi.WorkingDirectory = appDir;
        psi.UseShellExecute = true;
        try
        {
            Process.Start(psi);
        }
        catch (Exception ex)
        {
            return Fail("\u542f\u52a8\u5931\u8d25: " + ex.Message);
        }
        return 0;
    }
}
