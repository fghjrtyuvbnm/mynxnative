"""NIS records must retain exact control/code ranges, stages and archive bounds."""
import os,sys,struct,unittest,tempfile,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DM_GAME','01008D7016438000')
import split_nis_shaders as nis

def record(stage):
    ctl=bytearray(0x848);ctl[:4]=bytes.fromhex('34127698');struct.pack_into('<I',ctl,0x20,len(ctl));struct.pack_into('<I',ctl,0x704,0x100)
    code=bytearray(0x100);code[:4]=bytes.fromhex('78563412');struct.pack_into('<I',code,0x30,stage<<10|0x61)
    return b'NMPL_NVN\xc1\x1cSHADER'+struct.pack('<8I',0x30,0x30,0x878,0,len(ctl),len(code),0,0)+ctl+code

class NISInputs(unittest.TestCase):
    def test_embedded_unaligned_nmpl_programs_keep_both_stages(self):
        found=nis.scan_nmpl(b'prefix!'+record(1)+record(5),'main')
        self.assertEqual([r[1] for r in found],['vs','ps'])
        self.assertEqual([len(r[2]) for r in found],[0x848,0x848])
        self.assertEqual([len(r[3]) for r in found],[0x100,0x100])

    def test_truncated_and_overlapping_ranges_are_rejected(self):
        good=record(1)
        with self.assertRaises(ValueError): nis.scan_nmpl(good[:-1],'bad')
        bad=bytearray(good);struct.pack_into('<I',bad,0x18,0x40)
        with self.assertRaises(ValueError): nis.scan_nmpl(bad,'bad')

    def test_ykcmp_zlib_requires_exact_size_and_complete_stream(self):
        raw=b'NMPL_FX_SHADERDT'+bytes(48)+record(1)
        z=zlib.compress(raw)
        wrapped=struct.pack('<3I',1,0xffffffff,12)+b'YKCMP_V1'+struct.pack('<3I',7,len(z)+20,len(raw))+z
        self.assertEqual(nis.decode_effect(wrapped),raw)
        wrong=bytearray(wrapped);struct.pack_into('<I',wrong,28,len(raw)-1)
        with self.assertRaises(ValueError): nis.decode_effect(wrong)
        with self.assertRaises(ValueError): nis.decode_effect(wrapped[:-1])
        self.assertIsNone(nis.decode_effect(b'unrelated'))

    def test_archive_effect_is_scanned_and_member_bounds_checked(self):
        raw=b'NMPL_FX_SHADERDT'+bytes(48)+record(1)+record(5)
        z=zlib.compress(raw)
        member=struct.pack('<3I',1,0xffffffff,12)+b'YKCMP_V1'+struct.pack('<3I',7,len(z)+20,len(raw))+z
        name=b'effect.fxdat\0';data_at=40+len(name)+48
        header=struct.pack('<8sIIQQQ',b'FAFULLFS',1,0,40,len(name),40+len(name))
        entry=struct.pack('<6Q',0,0,0,len(member),data_at,0)
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'data.dat';p.write_bytes(header+name+entry+member)
            self.assertEqual(list(nis.effect_members(p)),[('effect.fxdat',raw)])
            self.assertEqual(len(nis.scan_file((str(p),'data.dat'))[1]),2)
            p.write_bytes(header+name+entry+member[:-1])
            with self.assertRaises(ValueError): list(nis.effect_members(p))

if __name__=='__main__':unittest.main()
