#!/usr/bin/python2.7

#import clewn.vim as vim; vim.pdb()
import wx
import urllib2
import os
import string
import sqlite3
from lxml import etree
from multiprocessing import Process, Queue
import time
import sys

class Parser:
    def __init__(self):
        self.reset()

    def reset(self):
        self.videos = []

    def parse(self, data):
        tree = etree.XML(data)
        for e in tree:
            if e.tag[-5:] == 'entry':
                for d in e:
                    if d.tag[-5:] == 'group':
                        title = None
                        durat = None
                        vidid = None
                        descr = None
                        for g in d:
                            if g.tag[-5:] == 'title':
                                title = g.text
                            elif g.tag[-8:] == 'duration':
                                durat = g.attrib['seconds']
                            elif g.tag[-7:] == 'videoid':
                                vidid = g.text
                            elif g.tag[-11:] == 'description':
                                descr = g.text
                        self.videos.append((title, durat, vidid, descr))
                        continue
                continue

    def GetData(self):
        return self.videos

class LinkButton(wx.Button):
    def SetLink(self, link):
        self.link = link

    def GetLink(self):
        return self.link

class ProxyDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, title='Proxy settings', size=(300, 170))

        co = sqlite3.connect('ymdata.db')
        cu = co.cursor()
        cu.execute('select * from proxy where selected==1')
        selected = cu.fetchall()
        cu.close()
        co.close()

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.proxyText = wx.TextCtrl(self) 
        self.portText = wx.TextCtrl(self)
        self.okButton = wx.Button(self, label='OK')
        self.Bind(wx.EVT_BUTTON, self.OnOk, self.okButton)

        sizer.Add(wx.StaticText(self, label='Proxy address:'), 0, wx.ALL, 5)
        sizer.Add(self.proxyText, 1, wx.ALL | wx.EXPAND, 5)
        sizer.Add(wx.StaticText(self, label='Proxy port:'), 0, wx.ALL, 5)
        sizer.Add(self.portText, 1, wx.ALL | wx.EXPAND, 5)
        sizer.Add(self.okButton, 0, wx.ALL, 5)

        self.proxyText.SetValue(selected[0][2])
        self.portText.SetValue(selected[0][3])
        self.SetSizer(sizer)
        self.Layout()

    def OnOk(self, e):
        co = sqlite3.connect('ymdata.db')
        cu = co.cursor()
        try:
            cu.execute('update proxy set addr="' + self.proxyText.GetValue() + '", port="' +\
                    self.portText.GetValue() + '" where selected==1')
            co.commit()
        except:
            dlg = wx.MessageDialog(self, 'Cannot save proxy settings!', 'Alert!')
            dlg.ShowModal()
        finally:
            cu.close()
            co.close()
        self.Close()

    def GetProxy(self):
        return self.proxyText.GetValue() + ':' + self.portText.GetValue()

class VideoPanel(wx.Panel):
    def __init__(self, parent, image, title, duration, description):
        wx.Panel.__init__(self, parent, style=wx.SIMPLE_BORDER)

        self.image = image
        self.title = title
        self.duration = duration
        self.description = description

        if image:
            self.bitmap = wx.BitmapFromImage(image)
            self.iw = image.GetSize()[0]
            self.SetSize(image.GetSize())
        else:
            self.bitmap = None
            self.iw = 0
        self.Bind(wx.EVT_PAINT, self.OnPaint)

        self.SetCursor(wx.StockCursor(wx.CURSOR_HAND))

    def OnPaint(self, e):
        dc = wx.PaintDC(self)
        if self.title:
            font = dc.GetFont()
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            dc.SetFont(font)
            dc.DrawText(self.title, self.iw+10, 10)
            font.SetWeight(wx.FONTWEIGHT_NORMAL)
            dc.SetFont(font)
        if self.duration:
            dc.DrawText(self.duration, self.iw+10, 30)
        if self.description:
            dc.DrawText(self.description, self.iw+10, 50)
        if self.bitmap:
            dc.DrawBitmap(self.bitmap, 0, 0)
        e.Skip()

    def Clone(self, parent):
        return VideoPanel(parent, self.image.Copy(), self.title, self.duration, self.description)
       
class VlcSettingsDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, title='Vlc settings')

class MplSettingsDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, title='Mplayer settings')

class SavedVideosFrame(wx.Frame):
    def __init__(self, parent):
        wx.Frame.__init__(self, parent, title='YouMgr video library')

        self.parent = parent
        self.bgSizer = wx.BoxSizer(wx.HORIZONTAL)

        self.resultsPanel = wx.ScrolledWindow(self)
        self.resultsPanel.SetScrollbars(20,20,50,50)
        self.resultsSizer = wx.BoxSizer(wx.VERTICAL)
        self.resultsPanel.SetSizer(self.resultsSizer)

        self.bgSizer.Add(self.resultsPanel, 1, wx.ALL | wx.EXPAND)

        self.SetSizer(self.bgSizer)

        self.ReadFromDb()

    def CloneAndAddPanel(self, pan):
        npan = pan.Clone(self.resultsPanel)
        npan.link = pan.link
        self.AddPanel(npan)

    def AddPanel(self, pan):
        pan.Bind(wx.EVT_LEFT_DOWN, self.parent.OnPlay)
        pan.Bind(wx.EVT_RIGHT_DOWN, self.OnContextMenu)
        self.resultsSizer.Add(pan, 1, wx.TOP | wx.EXPAND, 1)
        self.Layout()

    def OnDelete(self, e, pan):
        pan.Hide()
        self.resultsSizer.Detach(pan)
        self.resultsPanel.RemoveChild(pan)
        self.Layout()

    def SaveToDb(self):
        co = sqlite3.connect('movies.db')
        cu = co.cursor()
        try:
            cu.execute('delete from data')
            co.commit()
        except:
            dlg = wx.MessageDialog(self, 'Cannot clear database!')
            dlg.ShowModal()
        for p in self.resultsPanel.GetChildren():
            try:
                cu.execute('insert into data values ("' + p.link + '","' + p.title + '","' +\
                            p.duration + '","' + p.description + '",' + str(p.image.GetWidth()) +\
                            ',' + str(p.image.GetHeight()) + ',?)', [buffer(p.image.GetData())])
                co.commit()
            except:
                dlg = wx.MessageDialog(self, 'Cannot save video:\n' + p.title + '\nto the database!', 'Alert!')
                dlg.ShowModal()
        cu.close()
        co.close()
        self.Close()
        pass

    def ReadFromDb(self):
        co = sqlite3.connect('movies.db')
        cu = co.cursor()
        cu.execute('select * from data')
        data = cu.fetchall()
        cu.close()
        co.close()
        for d in data:
            pan = VideoPanel(self.resultsPanel, wx.ImageFromBuffer(d[4], d[5], d[6]), d[1], d[2], d[3])
            pan.link = d[0]
            self.AddPanel(pan)

    def OnContextMenu(self, e):
        pan = e.GetEventObject()
        menu = wx.Menu()
        deleteit = wx.MenuItem(menu, wx.ID_ANY, 'Delete')
        self.Bind(wx.EVT_MENU, lambda e: self.OnDelete(e, pan), deleteit)
        menu.AppendItem(deleteit)
        pan.PopupMenu(menu, e.GetPosition())

class MainFrame(wx.Frame):
    def __init__(self):
        wx.Frame.__init__(self, None, title='YouMgr', size=(500,500))

        self.retrieveProcess = None
        self.retrieveQueue = None
        self.retrieveTimer = None

        self.buttons = []
        self.proxyName = ':'
        self.oldText = ''
        self.index = 1
        self.cchannel = False
        self.gui = False
        self.fulscreen = False
        self.newsearch = False
        
        self.bgSizer = wx.BoxSizer(wx.VERTICAL)
        self.mainSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.optSizer = wx.BoxSizer(wx.HORIZONTAL)

        #opt sizer
        self.vlcBox = wx.CheckBox(self, label='vlc')
        self.Bind(wx.EVT_CHECKBOX, self.OnGuiChange, self.vlcBox)

        self.fscBox = wx.CheckBox(self, label='fulscreen')
        self.Bind(wx.EVT_CHECKBOX, self.OnFulscreenChange, self.fscBox)

        self.optSizer.Add(self.vlcBox, 0, wx.ALL, 5)
        self.optSizer.Add(self.fscBox, 0, wx.ALL, 5)

        #main sizer
        self.searchTxt = wx.TextCtrl(self)

        self.searchBtn = wx.Button(self, label='New search')
        self.Bind(wx.EVT_BUTTON, self.OnSearch, self.searchBtn)

        self.channelBx = wx.CheckBox(self, label='channel')
        self.Bind(wx.EVT_CHECKBOX, self.OnChannel, self.channelBx)

        self.resultsPanel = wx.ScrolledWindow(self)
        self.resultsPanel.SetScrollbars(20,20,50,50)
        self.resultsSizer = wx.BoxSizer(wx.VERTICAL)
        self.resultsPanel.SetSizer(self.resultsSizer)

        self.mainSizer.Add(self.searchTxt, 1, wx.ALL | wx.EXPAND, 5)
        self.mainSizer.Add(self.channelBx, 0, wx.ALL, 5)
        self.mainSizer.Add(self.searchBtn, 0, wx.ALL, 5)

        #background sizer
        self.bgSizer.Add(self.mainSizer, 0, wx.ALL | wx.EXPAND)
        self.bgSizer.Add(self.optSizer, 0, wx.ALL | wx.EXPAND)
        self.bgSizer.Add(self.resultsPanel, 1,  wx.ALL | wx.EXPAND, 5)

        #menus
        self.menuBar = wx.MenuBar()

        fileMenu = wx.Menu()
        proxyMenu = wx.MenuItem(fileMenu, wx.ID_ANY, '&Proxy')
        exitMenu = wx.MenuItem(fileMenu, wx.ID_EXIT, 'E&xit')

        playersMenu = wx.Menu()
        vlcMenu = wx.MenuItem(playersMenu, wx.ID_ANY, 'Vlc')
        mplMenu = wx.MenuItem(playersMenu, wx.ID_ANY, 'Mplayer')

        fileMenu.AppendItem(proxyMenu)
        fileMenu.AppendItem(exitMenu)
        self.Bind(wx.EVT_MENU, self.OnProxy, proxyMenu)
        self.Bind(wx.EVT_MENU, self.OnExit, exitMenu)

        playersMenu.AppendItem(vlcMenu)
        playersMenu.AppendItem(mplMenu)
        self.Bind(wx.EVT_MENU, self.OnVlcSettings, vlcMenu)
        self.Bind(wx.EVT_MENU, self.OnMplSettings, mplMenu)

        self.menuBar.Append(fileMenu, 'Options')
        self.menuBar.Append(playersMenu, 'Players')

        self.statusStrip = wx.StatusBar(self)
        self.statusStrip.SetStatusText('Ready')

        #settings dialogs
        self.proxyDlg = ProxyDialog(self)
        self.vlcDlg = VlcSettingsDialog(self)
        self.mplDlg = MplSettingsDialog(self)
        
        self.searchTxt.Bind(wx.EVT_KEY_DOWN, self.OnSearchKeyDown)

        #library window
        self.libraryWnd = SavedVideosFrame(self)
        self.libraryWnd.Show(True)

        self.SetSizer(self.bgSizer)
        self.SetMenuBar(self.menuBar)
        self.SetStatusBar(self.statusStrip)
        self.Layout()

    def OnVlcSettings(self, e):
        self.vlcDlg.ShowModal()

    def OnMplSettings(self, e):
        self.mplDlg.ShowModal()

    def OnGuiChange(self, e):
        self.gui = not self.gui

    def OnFulscreenChange(self, e):
        self.fulscreen = not self.fulscreen

    def OnTimer(self, e):
        while True:
            try:
                data = self.retrieveQueue.get_nowait()
            except:
                return
            if len(data) == 1:
                if data[0] == 'end':
                    print('Timer: End')
                elif data[0] == 'failed':
                    print('Timer: Failed')
                self.retrieveTimer.Stop()
                self.retrieveTimer.Destroy()
                self.retrieveQueue.close()

                #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
                # hmm?:
                self.retrieveProcess = None
                self.retrieveQueue = None
                self.retrieveTimer = None
            elif len(data) == 2:
                if data[1] != None:
                    image = wx.ImageFromData(data[1][0], data[1][1], data[1][2])
                    self.CreateButton(data[0], image)
                else:
                    self.CreateButton(data[0], None) 
        
    def OnChannel(self, e):
        if self.cchannel:
            self.cchannel = False
        else:
            self.cchannel = True

    def OnSearchKeyDown(self, e):
        key = e.GetKeyCode()
        if key == wx.WXK_RETURN:
            self.Search()
        else:
            e.Skip()

    def OnKeyDown(self, e):
        key = e.GetKeyCode()
        if key == wx.WXK_RETURN:
            print('enter')
        elif key == 'Q' or key == 'q':
            if e.ControlDown():
                self.Quit()
        else:
            e.Skip()

    def OnSearch(self, e):
        self.newsearch = True
        self.Search()

    def StoHMS(self, s):
        s = int(s)
        h = s / 3600
        s = s - h * 3600
        m = s / 60
        s = s - m * 60
        sh = str(h)
        if len(sh) < 2:
            sh = '0' + sh
        sm = str(m)
        if len(sm) < 2:
            sm = '0' + sm
        ss = str(s)
        if len(ss) < 2:
            ss = '0' + ss
        return sh + ':' + sm + ':' + ss

    def Search(self):
        if self.retrieveProcess != None:
            return

        text = self.searchTxt.GetValue()
        self.statusStrip.SetStatusText('Searching for: ' + text + '...')
        if text != self.oldText or self.cchannel or self.newsearch:
            self.resultsSizer.Clear(True)
            self.index = 1
            self.cchannel = False
            self.newsearch = False
        else:
            self.index = self.index + 10

        print(self.index)
        self.oldText = text
        text = self.PrepareQuery(text)

        if self.channelBx.GetValue():
            query = 'http://gdata.youtube.com/feeds/api/users/' + text + '/uploads?start-index=' + str(self.index) +\
                    '&max-results=10&v=2&prettyprint=true'
        else:
            query = 'http://gdata.youtube.com/feeds/api/videos?q=' + text + '&start-index=' + str(self.index) +\
                    '&max-results=10&v=2&prettyprint=true'
                
        self.proxyName = self.proxyDlg.GetProxy()
        
        self.retrieveTimer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnTimer, self.retrieveTimer)
        self.retrieveQueue = Queue()
        self.retrieveProcess = Process(target=Retrieve, args=(self.proxyName, self.retrieveQueue, query))
        self.retrieveProcess.start()
        self.retrieveTimer.Start(50)
    
    def CreateButton(self, data, image):
        title = data[0]
        time = self.StoHMS(data[1])
        link = 'http://www.youtube.com/watch?v=' + data[2]
        pan = VideoPanel(self.resultsPanel, image, title, time, data[3])
        pan.Bind(wx.EVT_LEFT_DOWN, self.OnPlay)
        pan.Bind(wx.EVT_RIGHT_DOWN, self.OnContextMenu)
        pan.link = link

        self.resultsSizer.Add(pan, 1, wx.TOP | wx.EXPAND, 1)
        self.Layout()

    def OnContextMenu(self, e):
        pan = e.GetEventObject()
        menu = wx.Menu()

        save = wx.MenuItem(menu, wx.ID_ANY, 'Save')
        self.Bind(wx.EVT_MENU, lambda e: self.OnSave(e, pan), save)

        download = wx.MenuItem(menu, wx.ID_ANY, 'Download')
        self.Bind(wx.EVT_MENU, lambda e: self.OnDownload(e, pan), download)

        menu.AppendItem(save)
        menu.AppendItem(download)
        pan.PopupMenu(menu, e.GetPosition())

    def OnSave(self, e, pan):
        self.libraryWnd.CloneAndAddPanel(pan)

    def OnDownload(self, e, pan):
        os.system('youtube-dl ' + pan.link + ' &')

    def OnPlay(self, e):
        link = '$(youtube-dl --get-url ' +  e.GetEventObject().link + ')'

        proxy = self.proxyDlg.GetProxy() 
        if proxy != ':':
            os.environ["http_proxy"] = self.proxyName
            os.environ["ftp_proxy"] = self.proxyName

        if self.gui:
            player = 'vlc'

            if self.fulscreen:
                player = player + ' -f'

            if proxy != ':':
                proxy = '--http-proxy=' + proxy + ' '
            else:
                proxy = ''

            print(player + ' ' + proxy + link + ' &')
            os.system(player + ' ' + proxy + link + ' &')
        else:
            player = 'mplayer'

            if self.fulscreen:
                player = player + ' -fs'

            player = player + ' -cache 10000'

            proxy = self.proxyDlg.GetProxy() 
            if proxy != ':':
                proxy = 'http_proxy://' + proxy + '/'
            else:
                proxy = ''

            print(player + ' -volume 50 ' + proxy + link + ' &')
            os.system(player + ' -volume 50 ' + proxy + link + ' &')

    def PrepareQuery(self, text):
        wasWhite = True
        newText = ''
        for c in text:
            if c == ' ':
                if wasWhite:
                    continue
                else:
                    newText = newText + '+'
                    wasWhite = True
            else:
                newText = newText + c 
                wasWhite = False

        return newText.strip('+')

    def OnProxy(self, e):
        self.proxyDlg.ShowModal()
        self.proxyName = self.proxyDlg.GetProxy()
        pass

    def OnExit(self, e):
        self.Quit()

    def Quit(self):
        self.libraryWnd.SaveToDb()
        exit()

def Retrieve(proxy, queue, url):
    data = None
    try:
        data = FetchURL(proxy, url).read()
    except: 
        queue.put(['failed'])
        return

    p = Parser()
    p.parse(data)
    data = p.GetData()

    for d in data:
        image = RetrieveImageData(proxy, d)
        queue.put([d, image])
    queue.put(['end'])
    queue.close()

def RetrieveImageData(proxy, data):
    thumb = 'http://i.ytimg.com/vi/' + data[2] + '/default.jpg'
    try:
        image = wx.ImageFromStream(FetchURL(proxy, thumb), type=wx.BITMAP_TYPE_JPEG)
        return (image.GetWidth(), image.GetHeight(), image.GetData())
    except:
        return None

def FetchURL(proxy, url):
    if proxy != ':':
        return urllib2.build_opener(urllib2.ProxyHandler({'http': proxy })).open(url)
    else:
        return urllib2.urlopen(url)

app = wx.App(False)
wnd = MainFrame()
wnd.Show(True)
wnd.Maximize()
app.MainLoop()
